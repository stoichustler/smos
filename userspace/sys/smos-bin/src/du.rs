use std::fs::{self, Metadata};
use std::path::Path;

fn usage() -> ! {
    eprintln!("Usage: du [-a | -s] [-d depth] [-h] [-k] [-x] [file ...]");
    std::process::exit(1);
}
fn blocks(meta: &Metadata, unit: u64) -> u64 {
    (meta.len().saturating_add(unit - 1)) / unit
}
fn human(n: u64) -> String {
    let mut value = n as f64;
    let units = ["B", "KB", "MB", "GB", "TB"];
    let mut i = 0;
    while value >= 1024.0 && i + 1 < units.len() {
        value /= 1024.0;
        i += 1;
    }
    if i == 0 {
        format!("{}{}", n, units[i])
    } else {
        format!("{value:.1}{}", units[i])
    }
}
fn is_service_namespace(path: &Path) -> bool {
    path.file_name().is_some_and(|name| name == "svc")
        && path.parent().map_or(true, |parent| parent.components().count() <= 1)
}
fn walk(
    path: &Path,
    depth: usize,
    maxdepth: Option<usize>,
    all: bool,
    summary: bool,
    humanize: bool,
    unit: u64,
    total: &mut u64,
) {
    if is_service_namespace(path) {
        return;
    }
    let meta = match fs::symlink_metadata(path) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("du: {}: {e}", path.display());
            return;
        }
    };
    let mut size = blocks(&meta, unit);
    if meta.is_dir() {
        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                let mut child = 0;
                walk(&entry.path(), depth + 1, maxdepth, all, summary, humanize, unit, &mut child);
                size += child;
            }
        }
    }
    *total = size;
    if !summary && depth > 0 && maxdepth.map_or(true, |d| depth <= d) && (meta.is_dir() || all) {
        if humanize {
            println!("{}\t{}", human(size * unit), path.display());
        } else {
            println!("{}\t{}", size, path.display());
        }
    }
}
fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let mut all = false;
    let mut summary = false;
    let mut humanize = false;
    let mut unit = 512u64;
    let mut maxdepth = None;
    let mut paths = Vec::new();
    let mut i = 0;
    while i < args.len() {
        match args[i].to_str() {
            Some("-a") => all = true,
            Some("-s") => summary = true,
            Some("-h") => humanize = true,
            Some("-k") => unit = 1024,
            Some("-x") | Some("-H") | Some("-L") | Some("-P") => {}
            Some("-d") => {
                i += 1;
                maxdepth = Some(
                    args.get(i)
                        .and_then(|x| x.to_str())
                        .and_then(|x| x.parse().ok())
                        .unwrap_or_else(|| usage()),
                );
            }
            Some("--") => {
                paths.extend(args[i + 1..].iter().cloned());
                break;
            }
            Some(s) if s.starts_with('-') => usage(),
            _ => paths.push(args[i].clone()),
        }
        i += 1;
    }
    if all && summary || summary && maxdepth.is_some() {
        usage();
    }
    if paths.is_empty() {
        paths.push(".".into());
    }
    for path in paths {
        let mut total = 0;
        walk(Path::new(&path), 0, maxdepth, all, summary, humanize, unit, &mut total);
        if humanize {
            println!("{}\t{}", human(total * unit), path.to_string_lossy());
        } else {
            println!("{}\t{}", total, path.to_string_lossy());
        }
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use super::{human, is_service_namespace};

    #[test]
    fn skips_service_namespace() {
        assert!(is_service_namespace(Path::new("./svc")));
        assert!(is_service_namespace(Path::new("/svc")));
        assert!(!is_service_namespace(Path::new("./boot/svc")));
        assert!(!is_service_namespace(Path::new("./boot")));
    }

    #[test]
    fn uses_explicit_binary_units() {
        assert_eq!(human(0), "0B");
        assert_eq!(human(1024), "1.0KB");
        assert_eq!(human(1024 * 1024), "1.0MB");
        assert_eq!(human(1024 * 1024 * 1024), "1.0GB");
    }
}
