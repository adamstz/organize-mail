// Frontend logger that can send logs to backend for display in the log viewer

type LogLevel = 'debug' | 'info' | 'warning' | 'error';

class FrontendLogger {
  private sendToBackend(level: LogLevel, message: string) {
    // Send log to backend asynchronously (fire and forget)
    // Use relative path to work with Vite proxy
    try {
      fetch('/api/frontend-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          level: level.toUpperCase(),
          message: `[Frontend] ${message}`,
          timestamp: new Date().toISOString()
        })
      }).catch((err) => {
        // Log to console if backend is not available
        console.debug('Failed to send log to backend:', err);
      });
    } catch (err) {
      console.debug('Error sending log to backend:', err);
    }
  }

  private logToConsole(level: LogLevel, message: string, ...args: any[]) {
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${level.toUpperCase()}]`;
    
    switch (level) {
      case 'debug':
        console.debug(prefix, message, ...args);
        break;
      case 'info':
        console.info(prefix, message, ...args);
        this.sendToBackend(level, message);
        break;
      case 'warning':
        console.warn(prefix, message, ...args);
        this.sendToBackend(level, message);
        break;
      case 'error':
        console.error(prefix, message, ...args);
        this.sendToBackend(level, message);
        break;
    }
  }

  debug(message: string, ...args: any[]) {
    this.logToConsole('debug', message, ...args);
  }

  info(message: string, ...args: any[]) {
    this.logToConsole('info', message, ...args);
  }

  warning(message: string, ...args: any[]) {
    this.logToConsole('warning', message, ...args);
  }

  error(message: string, ...args: any[]) {
    this.logToConsole('error', message, ...args);
  }
}

export const logger = new FrontendLogger();
