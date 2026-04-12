use std::collections::HashMap;
use std::process::Stdio;

use anyhow::{Context, Result};

/// Manages agent processes — worktree creation and harness spawning.
pub struct AgentSpawner {
    /// agent_id → (sprint_id, pid)
    processes: HashMap<String, (String, u32)>,
}

impl AgentSpawner {
    pub fn new() -> Self {
        Self {
            processes: HashMap::new(),
        }
    }

    /// Spawn an agent: create git worktree, then start caloron-harness.
    pub async fn spawn(
        &mut self,
        sprint_id: &str,
        task_id: &str,
        agent_id: &str,
        _repo: &str,
        worktree_base: &str,
    ) -> Result<u32> {
        let worktree_path = format!("{worktree_base}/{agent_id}-{sprint_id}");
        let branch_name = format!("agent/{agent_id}/{sprint_id}");

        // Step 1: Create git worktree (if not already exists)
        if !std::path::Path::new(&worktree_path).exists() {
            let output = std::process::Command::new("git")
                .args(["worktree", "add", &worktree_path, "-b", &branch_name])
                .output()
                .context("Failed to create git worktree")?;

            if !output.status.success() {
                let stderr = String::from_utf8_lossy(&output.stderr);
                // Branch may already exist
                if stderr.contains("already exists") {
                    let output = std::process::Command::new("git")
                        .args(["worktree", "add", &worktree_path, &branch_name])
                        .output()
                        .context("Failed to create worktree with existing branch")?;
                    if !output.status.success() {
                        anyhow::bail!(
                            "Failed to create worktree: {}",
                            String::from_utf8_lossy(&output.stderr)
                        );
                    }
                } else {
                    anyhow::bail!("Failed to create worktree: {stderr}");
                }
            }

            tracing::info!(worktree_path, branch_name, "Created git worktree");
        }

        // Step 2: Start caloron-harness in the worktree
        let shell_url =
            std::env::var("CALORON_SHELL_URL").unwrap_or_else(|_| "http://localhost:7710".into());

        let child = tokio::process::Command::new("caloron-harness")
            .arg("start")
            .env("CALORON_AGENT_ID", agent_id)
            .env("CALORON_AGENT_ROLE", agent_id)
            .env("CALORON_TASK_ID", task_id)
            .env("CALORON_SPRINT_ID", sprint_id)
            .env("CALORON_SHELL_URL", &shell_url)
            .env("CALORON_WORKTREE", &worktree_path)
            .current_dir(&worktree_path)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .context("Failed to spawn caloron-harness")?;

        let pid = child.id().unwrap_or(0);

        self.processes
            .insert(agent_id.to_string(), (sprint_id.to_string(), pid));

        tracing::info!(agent_id, task_id, pid, "Harness process started");

        Ok(pid)
    }

    /// List all known agent processes.
    pub fn list_agents(&self) -> Vec<(String, String, u32)> {
        self.processes
            .iter()
            .map(|(id, (sprint, pid))| (id.clone(), sprint.clone(), *pid))
            .collect()
    }

    /// Kill an agent process.
    #[allow(dead_code)]
    pub fn kill(&mut self, agent_id: &str) -> Result<()> {
        if let Some((_, pid)) = self.processes.remove(agent_id) {
            unsafe {
                libc_kill(pid);
            }
            tracing::info!(agent_id, pid, "Agent killed");
        }
        Ok(())
    }
}

/// Check if a process is still alive.
pub fn is_process_alive(pid: u32) -> bool {
    // kill(pid, 0) checks existence without sending a signal
    unsafe { libc_kill_check(pid) }
}

#[cfg(unix)]
#[allow(dead_code)]
unsafe fn libc_kill(pid: u32) {
    unsafe { libc::kill(pid as i32, libc::SIGTERM) };
}

#[cfg(unix)]
unsafe fn libc_kill_check(pid: u32) -> bool {
    unsafe { libc::kill(pid as i32, 0) == 0 }
}

#[cfg(not(unix))]
unsafe fn libc_kill(_pid: u32) {}

#[cfg(not(unix))]
unsafe fn libc_kill_check(_pid: u32) -> bool {
    false
}
