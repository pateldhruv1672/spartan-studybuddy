# Spartan StudyBuddy VS Code Extension

1. Open this folder in VS Code and run `npm install -g @vscode/vsce` if you want a VSIX.
2. Set `spartan.api`, `spartan.projectId`, and `spartan.userId` in VS Code settings.
3. Press F5 from an Extension Development Host, or package with `vsce package`.
4. Use the StudyBuddy sidebar, `Spartan StudyBuddy: Index Workspace`, or save files with `spartan.indexOnSave=true`.

The extension sends only opted-in workspace source text to your own StudyBuddy backend. It never sends code to a third-party AI API.
