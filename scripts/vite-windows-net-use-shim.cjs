const childProcess = require("node:child_process");
const { EventEmitter } = require("node:events");

const originalExec = childProcess.exec;

childProcess.exec = function patchedExec(command, options, callback) {
  const commandText = Array.isArray(command) ? command.join(" ") : String(command);
  const maybeCallback = typeof options === "function" ? options : callback;
  if (process.platform === "win32" && commandText.trim().toLowerCase() === "net use") {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    queueMicrotask(() => {
      if (maybeCallback) maybeCallback(null, "", "");
      child.emit("close", 0);
      child.emit("exit", 0);
    });
    return child;
  }
  return originalExec(command, options, callback);
};
