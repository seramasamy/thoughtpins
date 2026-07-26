const childProcess = require("node:child_process");
const { EventEmitter } = require("node:events");

const originalExec = childProcess.exec;

childProcess.exec = function patchedExec(command, ...args) {
  if (
    process.platform === "win32" &&
    typeof command === "string" &&
    command.trim().toLowerCase() === "net use"
  ) {
    const callback = typeof args[args.length - 1] === "function" ? args[args.length - 1] : null;
    const child = new EventEmitter();
    child.pid = 0;
    child.kill = () => false;
    process.nextTick(() => {
      if (callback) callback(null, "There are no entries in the list.\n", "");
      child.emit("close", 0);
      child.emit("exit", 0);
    });
    return child;
  }
  return originalExec.call(this, command, ...args);
};
