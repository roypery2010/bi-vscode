import * as vscode from 'vscode';
import { exec } from 'child_process';

export function activate(context: vscode.ExtensionContext) {
  let disposable = vscode.commands.registerCommand('bi.runFile', () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const filePath = editor.document.fileName;
    const terminal = vscode.window.createTerminal("Run bi");
    terminal.show();
    terminal.sendText(`python bi.py "${filePath}"`);
  });

  context.subscriptions.push(disposable);
}

export function deactivate() {}
