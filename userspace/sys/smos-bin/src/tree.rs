use std::cmp::Ordering;
use std::ffi::{OsStr, OsString};
use std::fs::{self, DirEntry, Metadata};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

#[derive(Clone, Debug, Default, PartialEq, Eq)]
struct Options {
    all: bool,
    dirs_only: bool,
    max_depth: Option<usize>,
    full_path: bool,
    no_indent: bool,
    dirs_first: bool,
    classify: bool,
    paths: Vec<PathBuf>,
}

#[derive(Clone)]
struct Entry {
    path: PathBuf,
    name: OsString,
    metadata: Metadata,
}

#[derive(Default, Debug, PartialEq, Eq)]
struct Counts {
    directories: usize,
    files: usize,
}

fn usage() -> ! {
    eprintln!("Usage: tree [-adfFi] [--dirsfirst] [-L level] [path ...]");
    std::process::exit(1);
}

fn parse_args<I>(args: I) -> Result<Options, String>
where
    I: IntoIterator<Item = OsString>,
{
    let args: Vec<OsString> = args.into_iter().collect();
    let mut options = Options::default();
    let mut parse_options = true;
    let mut index = 0;
    while index < args.len() {
        let arg = &args[index];
        let text = arg.to_string_lossy();
        if parse_options && arg == OsStr::new("--") {
            parse_options = false;
            index += 1;
            continue;
        }
        if parse_options && text.starts_with('-') && text != "-" {
            if text == "--dirsfirst" {
                options.dirs_first = true;
            } else if let Some(value) = text.strip_prefix("--level=") {
                options.max_depth = Some(parse_level(value)?);
            } else if text.starts_with("--") {
                return Err(format!("unknown option: {text}"));
            } else {
                let short = &text[1..];
                let mut chars = short.chars();
                while let Some(option) = chars.next() {
                    match option {
                        'a' => options.all = true,
                        'd' => options.dirs_only = true,
                        'f' => options.full_path = true,
                        'F' => options.classify = true,
                        'i' => options.no_indent = true,
                        'L' => {
                            let value: String = chars.collect();
                            let value = if value.is_empty() {
                                index += 1;
                                args.get(index)
                                    .ok_or_else(|| "option -L requires a level".to_string())?
                                    .to_string_lossy()
                                    .into_owned()
                            } else {
                                value
                            };
                            options.max_depth = Some(parse_level(&value)?);
                            break;
                        }
                        _ => return Err(format!("unknown option: -{option}")),
                    }
                }
            }
        } else {
            options.paths.push(PathBuf::from(arg));
        }
        index += 1;
    }
    if options.paths.is_empty() {
        options.paths.push(PathBuf::from("."));
    }
    Ok(options)
}

fn parse_level(value: &str) -> Result<usize, String> {
    value.parse().map_err(|_| format!("invalid level: {value}"))
}

fn is_hidden(name: &OsStr) -> bool {
    name.to_string_lossy().starts_with('.')
}

fn is_executable(metadata: &Metadata) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        metadata.permissions().mode() & 0o111 != 0
    }
    #[cfg(not(unix))]
    {
        let _ = metadata;
        false
    }
}

fn suffix(entry: &Entry, classify: bool) -> &'static str {
    if !classify {
        return "";
    }
    if entry.metadata.file_type().is_symlink() {
        "@"
    } else if entry.metadata.is_dir() {
        "/"
    } else if is_executable(&entry.metadata) {
        "*"
    } else {
        ""
    }
}

fn entry_name(path: &Path, name: &OsStr, metadata: &Metadata, options: &Options) -> String {
    let mut value = if options.full_path {
        path.to_string_lossy().into_owned()
    } else {
        name.to_string_lossy().into_owned()
    };
    let entry =
        Entry { path: path.to_path_buf(), name: name.to_os_string(), metadata: metadata.clone() };
    value.push_str(suffix(&entry, options.classify));
    value
}

fn read_entries(path: &Path, options: &Options) -> io::Result<Vec<Entry>> {
    let mut entries = Vec::new();
    for result in fs::read_dir(path)? {
        let dir_entry: DirEntry = result?;
        let name = dir_entry.file_name();
        if !options.all && is_hidden(&name) {
            continue;
        }
        let child_path = dir_entry.path();
        let metadata = fs::symlink_metadata(&child_path)?;
        if options.dirs_only && !metadata.is_dir() {
            continue;
        }
        entries.push(Entry { path: child_path, name, metadata });
    }
    sort_entries(&mut entries, options.dirs_first);
    Ok(entries)
}

fn sort_entries(entries: &mut [Entry], dirs_first: bool) {
    entries.sort_by(|left, right| {
        let type_order = if dirs_first {
            right.metadata.is_dir().cmp(&left.metadata.is_dir())
        } else {
            Ordering::Equal
        };
        type_order.then_with(|| compare_names(&left.name, &right.name))
    });
}

fn compare_names(left: &OsStr, right: &OsStr) -> Ordering {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        left.as_bytes().cmp(right.as_bytes())
    }
    #[cfg(not(unix))]
    {
        left.to_string_lossy().cmp(&right.to_string_lossy())
    }
}

fn print_node<W: Write>(
    writer: &mut W,
    path: &Path,
    name: &OsStr,
    metadata: &Metadata,
    options: &Options,
    prefix: &str,
    is_last: bool,
    level: usize,
    counts: &mut Counts,
) -> io::Result<bool> {
    if metadata.is_dir() {
        counts.directories += 1;
    } else {
        counts.files += 1;
    }
    let connector = if level == 0 || options.no_indent {
        ""
    } else if is_last {
        "└── "
    } else {
        "├── "
    };
    writeln!(writer, "{prefix}{connector}{}", entry_name(path, name, metadata, options))?;

    if !metadata.is_dir() || options.max_depth.is_some_and(|depth| level >= depth) {
        return Ok(false);
    }
    let entries = match read_entries(path, options) {
        Ok(entries) => entries,
        Err(error) => {
            eprintln!("tree: {}: {error}", path.display());
            return Ok(true);
        }
    };
    let mut had_error = false;
    for (index, entry) in entries.iter().enumerate() {
        let child_prefix = if options.no_indent || level == 0 {
            prefix.to_string()
        } else {
            format!("{prefix}{}", if is_last { "    " } else { "│   " })
        };
        had_error |= print_node(
            writer,
            &entry.path,
            &entry.name,
            &entry.metadata,
            options,
            &child_prefix,
            index + 1 == entries.len(),
            level + 1,
            counts,
        )?;
    }
    Ok(had_error)
}

fn summary(counts: &Counts) -> String {
    format!(
        "{}, {}",
        if counts.directories == 1 {
            "1 directory".to_string()
        } else {
            format!("{} directories", counts.directories)
        },
        if counts.files == 1 { "1 file".to_string() } else { format!("{} files", counts.files) }
    )
}

fn run<I>(args: I) -> i32
where
    I: IntoIterator<Item = OsString>,
{
    let options = match parse_args(args) {
        Ok(options) => options,
        Err(error) => {
            eprintln!("tree: {error}");
            usage();
        }
    };
    let stdout = io::stdout();
    let mut writer = io::BufWriter::new(stdout.lock());
    let mut status = 0;
    for path in &options.paths {
        let metadata = match fs::symlink_metadata(path) {
            Ok(metadata) => metadata,
            Err(error) => {
                eprintln!("tree: {}: {error}", path.display());
                status = 1;
                continue;
            }
        };
        let root_name = path.as_os_str();
        let mut counts = Counts::default();
        match print_node(
            &mut writer,
            path,
            root_name,
            &metadata,
            &options,
            "",
            true,
            0,
            &mut counts,
        ) {
            Ok(had_error) => {
                if had_error {
                    status = 1;
                }
            }
            Err(error) => {
                eprintln!("tree: stdout: {error}");
                status = 1;
                break;
            }
        }
        if let Err(error) = writeln!(writer, "{}", summary(&counts)) {
            eprintln!("tree: stdout: {error}");
            status = 1;
            break;
        }
    }
    if let Err(error) = writer.flush() {
        eprintln!("tree: stdout: {error}");
        status = 1;
    }
    status
}

fn main() {
    std::process::exit(run(std::env::args_os().skip(1)));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_clustered_options_and_paths() {
        let options =
            parse_args([OsString::from("-adF"), OsString::from("-L2"), OsString::from("root")])
                .unwrap();
        assert!(options.all && options.dirs_only && options.classify);
        assert_eq!(options.max_depth, Some(2));
        assert_eq!(options.paths, vec![PathBuf::from("root")]);
    }

    #[test]
    fn defaults_to_current_directory() {
        assert_eq!(parse_args(std::iter::empty()).unwrap().paths, vec![PathBuf::from(".")]);
    }

    #[test]
    fn summarizes_singular_and_plural_counts() {
        assert_eq!(summary(&Counts { directories: 1, files: 1 }), "1 directory, 1 file");
        assert_eq!(summary(&Counts { directories: 2, files: 3 }), "2 directories, 3 files");
    }

    #[test]
    fn sorts_directories_first_when_requested() {
        let mut entries = vec![
            Entry {
                path: PathBuf::from("README.md"),
                name: OsString::from("README.md"),
                metadata: fs::metadata("README.md").unwrap(),
            },
            Entry {
                path: PathBuf::from("userspace"),
                name: OsString::from("userspace"),
                metadata: fs::metadata("userspace").unwrap(),
            },
        ];
        sort_entries(&mut entries, true);
        assert!(entries[0].metadata.is_dir());
    }

    #[test]
    fn renders_root_and_honors_max_depth() {
        let root = std::env::temp_dir().join(format!("smos-tree-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("child/grandchild")).unwrap();
        fs::write(root.join("child/grandchild/file"), b"x").unwrap();
        let options = Options { max_depth: Some(1), ..Options::default() };
        let metadata = fs::symlink_metadata(&root).unwrap();
        let mut output = Vec::new();
        let mut counts = Counts::default();
        print_node(
            &mut output,
            &root,
            root.as_os_str(),
            &metadata,
            &options,
            "",
            true,
            0,
            &mut counts,
        )
        .unwrap();
        let output = String::from_utf8(output).unwrap();
        assert!(output.lines().next().unwrap().starts_with(&root.display().to_string()));
        assert!(output.contains("└── child"));
        assert!(!output.contains("grandchild"));
        assert_eq!(counts, Counts { directories: 2, files: 0 });
        fs::remove_dir_all(root).unwrap();
    }
}
