#!/bin/zsh
# Git worktree manager for remote development sessions
# Creates and manages git worktrees, then connects to remote machine for coding

vibe() {
    # Global constants
    LOCAL_WORKTREE_BASE="/Volumes/External/Repositories/_vibecoding"
    REMOTE_WORKTREE_BASE="/Volumes/My Shared Files/_vibecoding"

    # Check for --cli option
    if [ "$1" = "--cli" ]; then
        if [ $# -eq 1 ]; then
            # No worktree specified, just SSH to home
            echo "Connecting to vibecoding.local..."
            ssh -i ~/.ssh/id_vibecoding nonstrict@vibecoding.local
            return 0
        elif [ $# -eq 3 ]; then
            # Repository and worktree specified, SSH and cd to worktree
            REPO_NAME="$2"
            WORKTREE_NAME="$3"
            echo "Connecting to vibecoding.local and navigating to worktree..."
            ssh -i ~/.ssh/id_vibecoding nonstrict@vibecoding.local -t "cd '$REMOTE_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME' && zsh -l -i"
            return 0
        else
            echo "Error: Invalid arguments for --cli option"
            echo "Usage: vibe --cli [repo_name worktree_name]"
            return 1
        fi
    fi

    # Check if exactly one argument is provided
    if [ $# -ne 1 ]; then
        echo "Error: Please provide exactly one argument (worktree name)"
        echo "Usage: vibe <worktree_name>"
        echo "   or: vibe --cli [repo_name worktree_name]"
        return 1
    fi

    WORKTREE_NAME="$1"

    # Check if we're in a git repository (not needed for --cli option)
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        echo "Error: Not in a git repository"
        return 1
    fi

    # Get repository name for subdirectory organization
    REPO_ROOT=$(git rev-parse --show-toplevel)
    REPO_NAME=$(basename "$REPO_ROOT")

    # Check if worktree directory already exists
    if [ -d "$LOCAL_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME" ]; then
        echo "Worktree directory already exists at: $LOCAL_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME"
        echo "Checking if it's already a valid worktree..."
        
        # Check if it's already a git worktree
        if git worktree list | grep -q "$LOCAL_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME"; then
            echo "Directory is already a valid worktree"
        else
            echo "Error: Directory exists but is not a git worktree"
            echo "Please remove the directory or choose a different name"
            return 1
        fi
    else
        # Create the worktree
        echo "Creating worktree '$WORKTREE_NAME'..."
        
        # Ensure repository subdirectory exists
        mkdir -p "$LOCAL_WORKTREE_BASE/$REPO_NAME"
        
        # Check if this is a remote branch reference (e.g., origin/branch-name)
        if [[ "$WORKTREE_NAME" == origin/* ]]; then
            # Extract the branch name without origin/ prefix
            LOCAL_BRANCH_NAME="${WORKTREE_NAME#origin/}"
            
            # Check if the remote branch exists
            if git show-ref --verify --quiet refs/remotes/"$WORKTREE_NAME"; then
                echo "Found remote branch '$WORKTREE_NAME', creating local tracking branch '$LOCAL_BRANCH_NAME'..."
                if ! git worktree add -b "$LOCAL_BRANCH_NAME" "$LOCAL_WORKTREE_BASE/$REPO_NAME/$LOCAL_BRANCH_NAME" "$WORKTREE_NAME"; then
                    echo "Error: Failed to create worktree from remote branch"
                    return 1
                fi
                # Update WORKTREE_NAME to use the local branch name for the rest of the function
                WORKTREE_NAME="$LOCAL_BRANCH_NAME"
            else
                echo "Error: Remote branch '$WORKTREE_NAME' does not exist"
                echo "Available remote branches:"
                git branch -r | grep "origin/"
                return 1
            fi
        # Check if local branch already exists
        elif git show-ref --verify --quiet refs/heads/"$WORKTREE_NAME"; then
            # Branch exists, create worktree from existing branch
            if ! git worktree add "$LOCAL_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME" "$WORKTREE_NAME"; then
                echo "Error: Failed to create worktree"
                return 1
            fi
        else
            # Branch doesn't exist, create new branch and worktree
            if ! git worktree add -b "$WORKTREE_NAME" "$LOCAL_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME"; then
                echo "Error: Failed to create worktree"
                return 1
            fi
        fi
        
        echo "Worktree created successfully at: $LOCAL_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME"
    fi

    # SSH to remote machine and start vibe coding session
    echo "Connecting to vibecoding.local and starting cly..."
    ssh -i ~/.ssh/id_vibecoding nonstrict@vibecoding.local -t "cd '$REMOTE_WORKTREE_BASE/$REPO_NAME/$WORKTREE_NAME' && zsh -l -i -c \"cly\""
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