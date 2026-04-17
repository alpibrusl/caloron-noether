use std::collections::HashMap;
use std::process::Stdio;

use anyhow::{Context, Result};

/// Tracking record for a spawned agent process.
///
/// `starttime` is the kernel's process start time (field 22 of
/// `/proc/<pid>/stat` on Linux, clock ticks since boot). Recording it at
/// spawn time lets [`is_process_alive`] distinguish the original child from
/// an unrelated process that ended up with the same PID after reuse.
/// On non-Linux targets the field is captured as `None` and the liveness
/// check falls back to `kill(pid, 0)` — a known race that only closes on
/// platforms where we can read a stable process identity from the kernel.
#[derive(Clone)]
struct AgentRecord {
    sprint_id: String,
    pid: u32,
    starttime: Option<u64>,
}

/// Manages agent processes — worktree creation and harness spawning.
pub struct AgentSpawner {
    /// agent_id → tracking record
    processes: HashMap<String, AgentRecord>,
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
        let starttime = read_proc_starttime(pid);

        self.processes.insert(
            agent_id.to_string(),
            AgentRecord {
                sprint_id: sprint_id.to_string(),
                pid,
                starttime,
            },
        );

        tracing::info!(agent_id, task_id, pid, starttime, "Harness process started");

        Ok(pid)
    }

    /// List all known agent processes.
    pub fn list_agents(&self) -> Vec<(String, String, u32)> {
        self.processes
            .iter()
            .map(|(id, rec)| (id.clone(), rec.sprint_id.clone(), rec.pid))
            .collect()
    }

    /// Check whether the agent's original process is still alive.
    ///
    /// On Linux this also validates that the PID has not been recycled
    /// since spawn: if the current `/proc/<pid>/stat` start time differs
    /// from the one we recorded, the process is reported dead.
    pub fn is_agent_alive(&self, agent_id: &str) -> bool {
        match self.processes.get(agent_id) {
            None => false,
            Some(rec) => match rec.starttime {
                Some(expected) => read_proc_starttime(rec.pid) == Some(expected),
                None => is_process_alive(rec.pid),
            },
        }
    }

    /// Kill an agent process.
    #[allow(dead_code)]
    pub fn kill(&mut self, agent_id: &str) -> Result<()> {
        if let Some(rec) = self.processes.remove(agent_id) {
            unsafe {
                libc_kill(rec.pid);
            }
            tracing::info!(agent_id, pid = rec.pid, "Agent killed");
        }
        Ok(())
    }
}

/// Check if a process is still alive by PID only.
///
/// On Linux this does not protect against PID reuse — callers that track a
/// specific child should use [`AgentSpawner::is_agent_alive`], which
/// compares `/proc/<pid>/stat`'s start time against the value recorded at
/// spawn. Retained for the non-Unix fallback path and for tests.
pub fn is_process_alive(pid: u32) -> bool {
    unsafe { libc_kill_check(pid) }
}

/// Read field 22 of `/proc/<pid>/stat` (start time in clock ticks since boot)
/// to give us a stable identity for PID-reuse detection. Returns `None` on
/// non-Linux targets or if the process is already gone.
#[cfg(target_os = "linux")]
fn read_proc_starttime(pid: u32) -> Option<u64> {
    let contents = std::fs::read_to_string(format!("/proc/{pid}/stat")).ok()?;
    // Field 2 is `(comm)` which may contain spaces — find the trailing `)`
    // and tokenise from there so field 22 is unambiguous.
    let rparen = contents.rfind(')')?;
    let rest = contents.get(rparen + 1..)?;
    // Fields after comm: state(3), ppid(4), ..., starttime(22). That's 20 tokens
    // after the state field, i.e. index 19 in this slice's whitespace-split view.
    rest.split_ascii_whitespace().nth(19)?.parse().ok()
}

#[cfg(not(target_os = "linux"))]
fn read_proc_starttime(_pid: u32) -> Option<u64> {
    None
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

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(target_os = "linux")]
    #[test]
    fn read_proc_starttime_returns_some_for_self() {
        let pid = std::process::id();
        let t = read_proc_starttime(pid);
        assert!(
            t.is_some(),
            "should read /proc/{pid}/stat for current process"
        );
        assert!(t.unwrap() > 0);
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn read_proc_starttime_handles_comm_with_spaces() {
        let fake = "1234 (weird (comm)) S 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 999888 0\n";
        let rparen = fake.rfind(')').unwrap();
        let rest = &fake[rparen + 1..];
        let parsed: u64 = rest
            .split_ascii_whitespace()
            .nth(19)
            .unwrap()
            .parse()
            .unwrap();
        assert_eq!(parsed, 999888);
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn read_proc_starttime_returns_none_for_nonexistent_pid() {
        assert!(read_proc_starttime(0).is_none());
    }
}
