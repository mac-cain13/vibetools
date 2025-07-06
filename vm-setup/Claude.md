# Development Workflow

## Research → Plan → Ask Questions → Implement

**NEVER JUMP STRAIGHT TO CODING!** Always follow this sequence:

### 1. Research Phase
- Explore the codebase and understand existing patterns
- Use multiple agents for parallel exploration when beneficial
- Check for existing build/test commands and conventions

### 2. Planning & Question Phase  
- Create a detailed implementation plan
- **IDENTIFY AMBIGUITIES** - ask 3-5 clarifying questions about unclear aspects
- **Present plan for approval** if complex or ambiguous
- If straightforward and clear, proceed directly to implementation

### 3. Implementation Phase
- Execute plan with validation checkpoints
- Use TodoWrite tool for complex multi-step tasks (recommended for all non-trivial work)
- **Use multiple agents aggressively** - split work whenever tasks can be done in parallel

### 4. Validation Standards
- **Always attempt** to run build commands automatically to verify compilation
- **Always attempt** to run tests if they exist 
- Verify the feature works as intended
- If builds fail, fix issues before completing the task

## Use Multiple Agents Aggressively

Leverage multiple agents whenever possible:
- Multi-file changes that aren't tightly coupled
- Research + implementation in parallel  
- Writing tests while implementing features
- Complex analysis + implementation
- Large codebase exploration

## Task Management

Use TodoWrite tool to:
- Break complex tasks into smaller steps
- Track progress transparently for the user
- Plan before implementing
- Show what's been completed

# Improved Xcode builds

You must always pipe any `xcodebuild` command you execute through `xcbeautify` for a more compact build output that easier to parse and gives better error information.

Example: 
  This: `xcodebuild -project Bezel.xcodeproj -scheme "iOS" -destination "platform=iOS Simulator,name=iPhone 16 Pro Max"`
  Should become: `xcodebuild -project Bezel.xcodeproj -scheme "iOS" -destination "platform=iOS Simulator,name=iPhone 16 Pro Max" | xcbeautify`

# Available tools

These tools and their dependencies are installed and available to use if you might need them: ripgrep jq fd fzf bat tree yq htmlq gh git-delta hyperfine watch tldr pandoc xcbeautify imagemagick ffmpeg
