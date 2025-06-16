#!/bin/zsh
# Git worktree manager for remote development sessions
# Creates and manages git worktrees, then connects to remote machine for coding

vibe() {
    # Global constants
    LOCAL_WORKTREE_BASE="/Volumes/External/Repositories/_vibecoding"
    REMOTE_WORKTREE_BASE="/Volumes/My Shared Files/_vibecoding"
    SSH_KEY_PATH="~/.ssh/id_vibecoding"
    SSH_USER_HOST="nonstrict@vibecoding.local"
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

    # Helper function to connect to remote
    _connect_to_remote() {
        local use_cly="$1"
        if [ "$use_cly" = "true" ]; then
            echo "Connecting to vibecoding.local and starting $CODING_TOOL_CMD..."
            ssh -i "$SSH_KEY_PATH" "$SSH_USER_HOST" -t "cd '$REMOTE_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME' && zsh -l -i -c \"$CODING_TOOL_CMD\""
        else
            echo "Connecting to vibecoding.local and navigating to worktree..."
            ssh -i "$SSH_KEY_PATH" "$SSH_USER_HOST" -t "cd '$REMOTE_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME' && zsh -l -i"
        fi
    }

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

    # Check if exactly one argument is provided
    if [ $# -ne 1 ]; then
        echo "Error: Please provide exactly one argument (worktree name)"
        echo "Usage: vibe <worktree_name>"
        echo "   or: vibe --cli [worktree_name]"
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
    
    # Only provide completions if we're in a git repository
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        return 1
    fi
    
    # Get all branch names (local and remote) and clean them up
    local branches
    local local_branches remote_branches
    
    # Get local branches
    local_branches=($(git branch --format='%(refname:short)' 2>/dev/null))
    
    # Get remote branches (both with and without origin/ prefix for convenience)
    remote_branches=($(git branch -r --format='%(refname:short)' 2>/dev/null | grep '^origin/' | sort -u))
    
    # Combine all branches
    branches=($local_branches $remote_branches)
    
    _describe 'git branches' branches
}

# Register the completion function
compdef _vibe vibe