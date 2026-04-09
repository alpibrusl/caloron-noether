use std::collections::HashMap;
use chrono::{DateTime, Utc};

/// In-memory heartbeat store with async KV persistence via Noether CLI.
pub struct HeartbeatStore {
    /// agent_id → (sprint_id, last_heartbeat, status)
    entries: HashMap<String, HeartbeatEntry>,
}

struct HeartbeatEntry {
    sprint_id: String,
    last_heartbeat: DateTime<Utc>,
    status: Option<String>,
}

impl HeartbeatStore {
    pub fn new() -> Self {
        Self {
            entries: HashMap::new(),
        }
    }

    /// Record a heartbeat from an agent.
    pub fn record(&mut self, agent_id: &str, sprint_id: &str, status: Option<&str>) {
        let now = Utc::now();

        self.entries.insert(
            agent_id.to_string(),
            HeartbeatEntry {
                sprint_id: sprint_id.to_string(),
                last_heartbeat: now,
                status: status.map(|s| s.to_string()),
            },
        );

        // Persist to Noether KV store (fire and forget)
        let key = format!("caloron:{sprint_id}:agent:{agent_id}:last_heartbeat");
        let value = now.to_rfc3339();
        tokio::spawn(async move {
            let _ = write_kv(&key, &value).await;
        });
    }

    /// Get the last heartbeat time for an agent.
    pub fn last_heartbeat(&self, agent_id: &str) -> Option<DateTime<Utc>> {
        self.entries.get(agent_id).map(|e| e.last_heartbeat)
    }
}

/// Write a value to the Noether KV store via the `noether` CLI.
///
/// Uses `noether stage run <kv_set_hash>` with the key/value as input.
/// Falls back to a direct SQLite write if the CLI is not available.
async fn write_kv(key: &str, value: &str) -> anyhow::Result<()> {
    // Try writing via a simple Python one-liner that uses Noether's KV
    // This avoids depending on a specific stage hash or graph file.
    let script = format!(
        r#"import sqlite3, json, os
db_path = os.path.expanduser("~/.noether/kv.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)
conn = sqlite3.connect(db_path)
conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)")
conn.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", ("{key}", json.dumps("{value}")))
conn.commit()
conn.close()
"#
    );

    let output = tokio::process::Command::new("python3")
        .args(["-c", &script])
        .output()
        .await?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        tracing::debug!(key, stderr = %stderr, "KV write failed (non-fatal)");
    }

    Ok(())
}
