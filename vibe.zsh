#!/bin/zsh
# Git worktree manager for remote development sessions
# Creates and manages git worktrees, then connects to remote machine for coding

vibe() {
    # Global constants
    LOCAL_WORKTREE_BASE="/Volumes/External/Repositories/_vibecoding"
    REMOTE_WORKTREE_BASE="/Volumes/_vibecoding"
    SSH_KEY_PATH="~/.ssh/id_vibecoding"
    SSH_USER_HOST="admin@vibecoding.local"
    CODING_TOOL_CMD="cly"

    # Helper function to validate git repository
    _validate_git_repo() {
        if ! git rev-parse --git-dir > /dev/null 2>&1; then
            echo "Error: Not in a git repository"
            return 1
        fi
    }

    # Helper function to get repository information
    _get_repo_info() {
        REPO_ROOT=$(git rev-parse --show-toplevel)
        REPO_NAME=$(basename "$REPO_ROOT")
    }

    # Helper function to check if worktree exists
    _check_worktree_exists() {
        local worktree_name="$1"
        if [ -d "$LOCAL_WORKTREE_BASE/$REPO_NAME/$worktree_name" ]; then
            echo "Worktree directory already exists at: $LOCAL_WORKTREE_BASE/$REPO_NAME/$worktree_name"
            echo "Checking if it's already a valid worktree..."
            
            # Check if it's already a git worktree
            if git worktree list | grep -q "$LOCAL_WORKTREE_BASE/$REPO_NAME/$worktree_name"; then
                echo "Directory is already a valid worktree"
                return 0
            else
                echo "Error: Directory exists but is not a git worktree"
                echo "Please remove the directory or choose a different name"
                return 1
            fi
        fi
        return 2  # Directory doesn't exist
    }

    # Helper function to create worktree
    _create_worktree() {
        local worktree_name="$1"
        echo "Creating worktree '$worktree_name'..."
        
        # Ensure repository subdirectory exists
        mkdir -p "$LOCAL_WORKTREE_BASE/$REPO_NAME"
        
        # Check if this is a remote branch reference (e.g., origin/branch-name)
        if [[ "$worktree_name" == origin/* ]]; then
            # Extract the branch name without origin/ prefix
            LOCAL_BRANCH_NAME="${worktree_name#origin/}"
            
            # Check if the remote branch exists
            if git show-ref --verify --quiet refs/remotes/"$worktree_name"; then
                echo "Found remote branch '$worktree_name', creating local tracking branch '$LOCAL_BRANCH_NAME'..."
                if ! git worktree add -b "$LOCAL_BRANCH_NAME" "$LOCAL_WORKTREE_BASE/$REPO_NAME/$LOCAL_BRANCH_NAME" "$worktree_name"; then
                    echo "Error: Failed to create worktree from remote branch"
                    return 1
                fi
                # Update WORKTREE_NAME to use the local branch name for the rest of the function
                WORKTREE_NAME="$LOCAL_BRANCH_NAME"
            else
                echo "Error: Remote branch '$worktree_name' does not exist"
                echo "Available remote branches:"
                git branch -r | grep "origin/"
                return 1
            fi
        # Check if local branch already exists
        elif git show-ref --verify --quiet refs/heads/"$worktree_name"; then
            # Branch exists, create worktree from existing branch
            if ! git worktree add "$LOCAL_WORKTREE_BASE/$REPO_NAME/$worktree_name" "$worktree_name"; then
                echo "Error: Failed to create worktree"
                return 1
            fi
        else
            # Branch doesn't exist, create new branch and worktree
            if ! git worktree add -b "$worktree_name" "$LOCAL_WORKTREE_BASE/$REPO_NAME/$worktree_name"; then
                echo "Error: Failed to create worktree"
                return 1
            fi
        fi
        
        echo "Worktree created successfully at: $LOCAL_WORKTREE_BASE/$REPO_NAME/$worktree_name"
    }

    # Helper function to check if worktree has uncommitted changes
    _has_uncommitted_changes() {
        local worktree_path="$1"
        
        # Change to the worktree directory and check git status
        if [ -d "$worktree_path" ]; then
            (cd "$worktree_path" && [ -n "$(git status --porcelain 2>/dev/null)" ])
        else
            return 1  # Directory doesn't exist, treat as no changes
        fi
    }

    # Helper function to check if directory is empty (ignoring .DS_Store)
    _is_directory_empty() {
        local dir="$1"
        
        # Check if directory exists
        if [ ! -d "$dir" ]; then
            return 1
        fi
        
        # Count files, excluding .DS_Store
        local file_count=$(find "$dir" -maxdepth 1 -type f ! -name ".DS_Store" | wc -l)
        local dir_count=$(find "$dir" -maxdepth 1 -type d ! -path "$dir" | wc -l)
        
        # Directory is empty if no files (except .DS_Store) and no subdirectories
        [ $file_count -eq 0 ] && [ $dir_count -eq 0 ]
    }

    # Helper function to remove a worktree
    _remove_worktree() {
        local worktree_path="$1"
        local repo_root="$2"
        
        # Verify the repository root exists
        if [ ! -d "$repo_root" ]; then
            return 1
        fi
        
        # Change to the repository root and remove the worktree
        if (cd "$repo_root" && git worktree remove "$worktree_path" 2>/dev/null); then
            # After successfully removing the worktree, check if parent directory is empty
            local parent_dir=$(dirname "$worktree_path")
            if _is_directory_empty "$parent_dir"; then
                # Remove any .DS_Store file if present
                rm -f "$parent_dir/.DS_Store" 2>/dev/null
                # Remove the empty directory
                if rmdir "$parent_dir" 2>/dev/null; then
                    # Return 2 to indicate parent directory was also removed
                    return 2
                fi
            fi
            return 0
        else
            return 1
        fi
    }

    # Helper function to clean all worktrees across all repositories
    _clean_all_worktrees() {
        echo "Cleaning worktrees in: $LOCAL_WORKTREE_BASE"
        echo ""
        
        if [ ! -d "$LOCAL_WORKTREE_BASE" ]; then
            echo "No worktree base directory found"
            return 0
        fi
        
        local cleaned_count=0
        local skipped_count=0
        
        # Iterate through all repository directories
        for repo_dir in "$LOCAL_WORKTREE_BASE"/*; do
            if [ ! -d "$repo_dir" ]; then
                continue
            fi
            
            local repo_name=$(basename "$repo_dir")
            local repo_has_worktrees=false
            
            # Find the original repository to get worktree list
            local original_repo=""
            
            # Look for any worktree in this repo directory to find the original repo
            for worktree_dir in "$repo_dir"/*; do
                if [ -d "$worktree_dir" ] && ([ -d "$worktree_dir/.git" ] || [ -f "$worktree_dir/.git" ]); then
                    # Get the main repository root from this worktree
                    local git_common_dir=$(cd "$worktree_dir" && git rev-parse --git-common-dir 2>/dev/null)
                    if [ -n "$git_common_dir" ]; then
                        # The common dir points to the main repo's .git directory
                        original_repo=$(dirname "$git_common_dir")
                        break
                    fi
                fi
            done
            
            if [ -z "$original_repo" ]; then
                continue
            fi
            
            # Get list of worktrees for this repository
            local worktree_list=$(cd "$original_repo" && git worktree list --porcelain 2>/dev/null)
            
            # Parse worktree list and check each one in our directory
            while IFS= read -r line; do
                if [[ "$line" =~ ^worktree\ (.*)$ ]]; then
                    local worktree_path="${match[1]}"
                    
                    # Check if this worktree is in our managed directory
                    if [[ "$worktree_path" == "$LOCAL_WORKTREE_BASE/$repo_name"/* ]]; then
                        local worktree_name=$(basename "$worktree_path")
                        
                        # Print repo header only when we find the first worktree
                        if [ "$repo_has_worktrees" = false ]; then
                            echo "[$repo_name]"
                            repo_has_worktrees=true
                        fi
                        
                        if _has_uncommitted_changes "$worktree_path"; then
                            echo "  [ SKIP  ] $worktree_name - has uncommitted changes"
                            ((skipped_count++))
                        else
                            _remove_worktree "$worktree_path" "$original_repo"
                            local remove_status=$?
                            if [ $remove_status -eq 0 ]; then
                                echo "  [CLEANED] $worktree_name"
                                ((cleaned_count++))
                            elif [ $remove_status -eq 2 ]; then
                                echo "  [CLEANED] $worktree_name + removed empty parent directory"
                                ((cleaned_count++))
                            else
                                echo "  [ FAIL  ] $worktree_name - could not remove"
                            fi
                        fi
                    fi
                fi
            done <<< "$worktree_list"
        done
        
        echo ""
        echo "Removed: $cleaned_count, Skipped: $skipped_count"
    }

    # Helper function to clean a specific worktree
    _clean_specific_worktree() {
        local worktree_name="$1"
        local worktree_path="$LOCAL_WORKTREE_BASE/$REPO_NAME/$worktree_name"
        
        echo "Cleaning worktree: $worktree_name"
        echo ""
        
        # Check if worktree exists
        if [ ! -d "$worktree_path" ]; then
            echo "Error: Worktree '$worktree_name' does not exist"
            return 1
        fi
        
        # Check if it's a valid worktree
        if ! git worktree list | grep -q "$worktree_path"; then
            echo "Error: '$worktree_name' is not a valid git worktree"
            return 1
        fi
        
        # Check for uncommitted changes
        if _has_uncommitted_changes "$worktree_path"; then
            echo "Cannot clean '$worktree_name' (uncommitted changes)"
            echo "Please commit or stash changes first"
            return 1
        fi
        
        # Remove the worktree
        _remove_worktree "$worktree_path" "$REPO_ROOT"
        local remove_status=$?
        if [ $remove_status -eq 0 ]; then
            echo "[CLEANED] Removed: $worktree_name"
        elif [ $remove_status -eq 2 ]; then
            echo "[CLEANED] Removed: $worktree_name (also cleaned empty parent directory)"
        else
            echo "[ FAIL  ] Could not remove '$worktree_name'"
            return 1
        fi
    }

    # Helper function to connect to remote
    _connect_to_remote() {
        local use_cly="$1"
        if [ "$use_cly" = "true" ]; then
            echo "Connecting to vibecoding.local and starting $CODING_TOOL_CMD..."
            ssh -i "$SSH_KEY_PATH" "$SSH_USER_HOST" -t "cd '$REMOTE_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME' && security -v unlock-keychain -p admin ~/Library/Keychains/login.keychain-db && zsh -l -i -c \"$CODING_TOOL_CMD\""
        else
            echo "Connecting to vibecoding.local and navigating to worktree..."
            ssh -i "$SSH_KEY_PATH" "$SSH_USER_HOST" -t "cd '$REMOTE_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME' && security -v unlock-keychain -p admin ~/Library/Keychains/login.keychain-db && zsh -l -i"
        fi
    }

    # Helper function to connect locally
    _connect_locally() {
        local original_dir="$PWD"
        local worktree_path="$LOCAL_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME"
        
        echo "Switching to local worktree and starting $CODING_TOOL_CMD..."
        
        # Run in subshell so directory change doesn't affect parent
        (cd "$worktree_path" && "$CODING_TOOL_CMD")
        local exit_code=$?
        
        echo "Returning to original directory..."
        return $exit_code
    }

    # Check for --clean option
    if [ "$1" = "--clean" ]; then
        if [ $# -eq 1 ]; then
            # No specific worktree specified, clean all
            _clean_all_worktrees
            return $?
        elif [ $# -eq 2 ]; then
            # Specific worktree specified, need to be in git repo
            WORKTREE_NAME="$2"
            
            # Validate git repository
            _validate_git_repo || return 1
            
            # Get repository information
            _get_repo_info
            
            # Clean the specific worktree
            _clean_specific_worktree "$WORKTREE_NAME"
            return $?
        else
            echo "Error: Invalid arguments for --clean option"
            echo "Usage: vibe --clean [worktree_name]"
            return 1
        fi
    fi

    # Check for --cli option
    if [ "$1" = "--cli" ]; then
        if [ $# -eq 1 ]; then
            # No worktree specified, just SSH to home
            echo "Connecting to vibecoding.local..."
            ssh -i "$SSH_KEY_PATH" "$SSH_USER_HOST"
            return 0
        elif [ $# -eq 2 ]; then
            # Worktree specified, need to be in git repo and follow same logic as main command
            WORKTREE_NAME="$2"
            
            # Validate git repository
            _validate_git_repo || return 1

            # Get repository information
            _get_repo_info
            
            # Check if worktree exists
            _check_worktree_exists "$WORKTREE_NAME"
            local exists_status=$?
            if [ $exists_status -eq 1 ]; then
                return 1
            elif [ $exists_status -eq 2 ]; then
                # Create the worktree
                _create_worktree "$WORKTREE_NAME" || return 1
            fi
            
            # Connect to remote
            _connect_to_remote false
            return 0
        else
            echo "Error: Invalid arguments for --cli option"
            echo "Usage: vibe --cli [worktree_name]"
            return 1
        fi
    fi

    # Check for --local option
    if [ "$1" = "--local" ]; then
        if [ $# -eq 2 ]; then
            # Worktree specified, need to be in git repo and follow same logic as main command
            WORKTREE_NAME="$2"
            
            # Validate git repository
            _validate_git_repo || return 1

            # Get repository information
            _get_repo_info
            
            # Check if worktree exists
            _check_worktree_exists "$WORKTREE_NAME"
            local exists_status=$?
            if [ $exists_status -eq 1 ]; then
                return 1
            elif [ $exists_status -eq 2 ]; then
                # Create the worktree
                _create_worktree "$WORKTREE_NAME" || return 1
            fi
            
            # Connect locally
            _connect_locally
            return $?
        else
            echo "Error: Invalid arguments for --local option"
            echo "Usage: vibe --local <worktree_name>"
            return 1
        fi
    fi

    # Check if exactly one argument is provided
    if [ $# -ne 1 ]; then
        echo "Error: Please provide exactly one argument (worktree name)"
        echo "Usage: vibe [worktree_name]"
        echo "   or: vibe --cli [worktree_name]"
        echo "   or: vibe --local [worktree_name]"
        echo "   or: vibe --clean [worktree_name]"
        return 1
    fi

    WORKTREE_NAME="$1"

    # Validate git repository
    _validate_git_repo || return 1

    # Get repository information
    _get_repo_info

    # Check if worktree exists
    _check_worktree_exists "$WORKTREE_NAME"
    local exists_status=$?
    if [ $exists_status -eq 1 ]; then
        return 1
    elif [ $exists_status -eq 2 ]; then
        # Create the worktree
        _create_worktree "$WORKTREE_NAME" || return 1
    fi

    # Connect to remote with cly
    _connect_to_remote true
}

# Completion function for vibe command
_vibe() {
    local context state line
    local -a options worktrees
    
    # Define the main options
    options=(
        '--cli:Connect to remote CLI'
        '--local:Work locally without SSH'
        '--clean:Clean worktrees without uncommitted changes'
    )
    
    # Handle argument parsing
    if [[ $CURRENT -eq 2 ]]; then
        # First argument - could be option or worktree name
        if ! git rev-parse --git-dir > /dev/null 2>&1; then
            # Not in git repo, only show options that don't require git
            _describe 'options' options
            return 0
        fi
        
        # In git repo - show options and branch names
        local branches
        local local_branches remote_branches
        
        # Get local branches
        local_branches=($(git branch --format='%(refname:short)' 2>/dev/null))
        
        # Get remote branches (both with and without origin/ prefix for convenience)
        remote_branches=($(git branch -r --format='%(refname:short)' 2>/dev/null | grep '^origin/' | sort -u))
        
        # Combine all branches
        branches=($local_branches $remote_branches)
        
        _alternative \
            'options:options:_describe "options" options' \
            'branches:git branches:_describe "branches" branches'
        
    elif [[ $CURRENT -eq 3 ]]; then
        # Second argument - depends on first argument
        case "$words[2]" in
            --clean)
                # For --clean, show existing worktrees in the current repo
                if git rev-parse --git-dir > /dev/null 2>&1; then
                    local repo_root=$(git rev-parse --show-toplevel)
                    local repo_name=$(basename "$repo_root")
                    local worktree_base="/Volumes/External/Repositories/_vibecoding"
                    
                    if [[ -d "$worktree_base/$repo_name" ]]; then
                        worktrees=($(ls "$worktree_base/$repo_name" 2>/dev/null))
                        _describe 'existing worktrees' worktrees
                    fi
                fi
                ;;
            --cli|--local)
                # For --cli and --local, show branch names like the main command
                if git rev-parse --git-dir > /dev/null 2>&1; then
                    local branches
                    local local_branches remote_branches
                    
                    # Get local branches
                    local_branches=($(git branch --format='%(refname:short)' 2>/dev/null))
                    
                    # Get remote branches
                    remote_branches=($(git branch -r --format='%(refname:short)' 2>/dev/null | grep '^origin/' | sort -u))
                    
                    # Combine all branches
                    branches=($local_branches $remote_branches)
                    
                    _describe 'git branches' branches
                fi
                ;;
        esac
    fi
}

# Register the completion function
compdef _vibe vibe