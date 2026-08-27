# rapidjson

This is Fuchsia's copy of [rapidjson](https://github.com/Tencent/rapidjson),
C++ JSON parser and generator library.

The root of this repository contains a copy of the `include` directory of the
upstream repo. If changing the repository structure, please keep in mind that
the upstream repo contains third-party elements (outside of `include`) under
non-standard license that we do not want to pull in.

Version: 973dc9c06dcd3d035ebd039cfb9ea457721ec213

## rolling forward

Grab a copy of the upstream repository:

```sh
git clone git@github.com:miloyip/rapidjson.git
cd rapidjson
```

, or update an existing copy:

```sh
cd rapidjson
git fetch origin
```

Checkout the version you want to pull in:

```sh
git checkout origin/version1.1.0
```

Copy the files over to Fuchsia's copy:

```sh
cd FUCHSIA_RAPIDJSON_DIR
rm -rf rapidjson
cp -r UPSTREAM_RAPIDJSON_DIR/include/rapidjson .
```

Update `BUILD.gn` as needed. Update this file to include the new version
of the repo. Run `git add .`, `git commit` and upload the roll for review.
