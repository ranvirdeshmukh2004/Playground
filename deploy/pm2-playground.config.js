// PM2 Ecosystem Config — Playground Server
// Usage: pm2 start ecosystem.config.js
// Place this file on the PLAYGROUND EC2 instance at ~/playground/ecosystem.config.js

module.exports = {
  apps: [
    {
      name: "playground",
      script: "main.py",
      interpreter: "/home/ubuntu/playground/.venv/bin/python3",
      cwd: "/home/ubuntu/playground",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      env: {
        HOME: "/home/ubuntu",
      },
      // Logging
      log_file: "/home/ubuntu/playground/logs/pm2-combined.log",
      out_file: "/home/ubuntu/playground/logs/pm2-out.log",
      error_file: "/home/ubuntu/playground/logs/pm2-error.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      kill_timeout: 10000,
    },
  ],
};
