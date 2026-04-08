use std::collections::HashMap;
use chrono::{DateTime, Utc};

/// In-memory heartbeat store. Also writes to Noether KV via CLI for persistence.
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

        // Also persist to Noether KV store (fire and forget)
        let key = format!("caloron:{sprint_id}:agent:{agent_id}:last_heartbeat");
        let value = now.to_rfc3339();
        tokio::spawn(async move {
            let _ = write_kv(&key, &serde_json::json!(value)).await;
        });
    }

    /// Get the last heartbeat time for an agent.
    pub fn last_heartbeat(&self, agent_id: &str) -> Option<DateTime<Utc>> {
        self.entries.get(agent_id).map(|e| e.last_heartbeat)
    }
}

/// Write a value to the Noether KV store via the CLI.
async fn write_kv(key: &str, value: &serde_json::Value) -> anyhow::Result<()> {
    let input = serde_json::json!({
        "key": key,
        "value": value
    });

    let output = tokio::process::Command::new("noether")
        .args(["run", "--input", &input.to_string(), "kv_set.json"])
        .output()
        .await?;

    if !output.status.success() {
        tracing::debug!(
            key,
            stderr = %String::from_utf8_lossy(&output.stderr),
            "KV write failed (non-fatal)"
        );
    }

    Ok(())
}
