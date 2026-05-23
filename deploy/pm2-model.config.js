// PM2 Ecosystem Config — Model Server
// Usage: pm2 start ecosystem.config.js
// Place this file on each MODEL EC2 instance at ~/ecosystem.config.js

module.exports = {
  apps: [
    {
      name: "model-api",
      script: "/home/ubuntu/agent_api.py",
      interpreter: "/home/ubuntu/llm-env/bin/python3",
      cwd: "/home/ubuntu",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000, // 5 seconds between restarts
      max_memory_restart: "3G",
      env: {
        HOME: "/home/ubuntu",
      },
      // Logging
      log_file: "/home/ubuntu/logs/model-api-combined.log",
      out_file: "/home/ubuntu/logs/model-api-out.log",
      error_file: "/home/ubuntu/logs/model-api-error.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      // Startup
      kill_timeout: 30000, // 30 seconds to shut down gracefully
    },
  ],
};
