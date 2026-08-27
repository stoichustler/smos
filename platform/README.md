# Platform directory guide

The `platform/` tree contains SMOS board definitions, reusable build
bundles, development guidance, and product assembly configurations. This page
is a directory-level map; the linked `BUILD.gn`, `.gni`, and README files are
the authoritative implementation details.

## Top-level directories

| Directory | Purpose | Entry point |
| --- | --- | --- |
| [`boards`](boards/) | Board configurations and board-specific input bundles. | [`boards/BUILD.gn`](boards/BUILD.gn) |
| [`bundles`](bundles/) | Reusable groups of platform artifacts, tools, and tests. | [`bundles/BUILD.gn`](bundles/BUILD.gn) |
| [`coding`](coding/) | Language, formatting, and development guidance. | [`coding/README.md`](coding/README.md) |
| [`products`](products/) | Product assembly configurations and product-specific components. | [`products/smos_boot.gni`](products/smos_boot.gni) |

---

Hustle Embedded OS.
