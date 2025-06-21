# Ask questions about ambiguities

When working on a plan for problems or tasks consider asking 5 questions about things that are unclear.

# Improved Xcode builds

You must always pipe any `xcodebuild` command you execute through `xcbeautify` for a more compact build output that easier to parse and gives better error information.

Example: 
  This: `xcodebuild -project Bezel.xcodeproj -scheme "iOS" -destination "platform=iOS Simulator,name=iPhone 16 Pro Max"`
  Should become: `xcodebuild -project Bezel.xcodeproj -scheme "iOS" -destination "platform=iOS Simulator,name=iPhone 16 Pro Max" | xcbeautify`
