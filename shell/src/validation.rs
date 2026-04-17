/// Identifier validation for request-boundary fields.
///
/// Any field that flows into a filesystem path, a branch name, or an
/// environment variable name must match `^[a-z0-9_-]{1,64}$`. Rejecting at
/// the handler boundary keeps path traversal (`../`), absolute paths, and
/// shell metacharacters out of downstream code entirely.
pub fn is_valid_id(s: &str) -> bool {
    let len = s.len();
    if len == 0 || len > 64 {
        return false;
    }
    s.bytes()
        .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_plain_ids() {
        assert!(is_valid_id("agent-001"));
        assert!(is_valid_id("sprint_2026_04"));
        assert!(is_valid_id("po"));
        assert!(is_valid_id("a"));
        assert!(is_valid_id(&"x".repeat(64)));
    }

    #[test]
    fn rejects_empty() {
        assert!(!is_valid_id(""));
    }

    #[test]
    fn rejects_over_64() {
        assert!(!is_valid_id(&"x".repeat(65)));
    }

    #[test]
    fn rejects_path_traversal() {
        assert!(!is_valid_id("../../../etc/passwd"));
        assert!(!is_valid_id(".."));
        assert!(!is_valid_id("a/b"));
        assert!(!is_valid_id("./foo"));
    }

    #[test]
    fn rejects_absolute_paths() {
        assert!(!is_valid_id("/etc/passwd"));
        assert!(!is_valid_id("/"));
    }

    #[test]
    fn rejects_shell_metacharacters() {
        for bad in [
            "a;b", "a|b", "a&b", "a$b", "a`b", "a b", "a\tb", "a\nb", "a'b", "a\"b", "a\\b",
        ] {
            assert!(!is_valid_id(bad), "should reject {bad:?}");
        }
    }

    #[test]
    fn rejects_uppercase() {
        assert!(!is_valid_id("Agent-1"));
        assert!(!is_valid_id("PO"));
    }

    #[test]
    fn rejects_unicode() {
        assert!(!is_valid_id("agént"));
        assert!(!is_valid_id("\u{202e}gnp"));
    }
}
