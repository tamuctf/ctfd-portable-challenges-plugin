# Portable Challenges Plugin

This plugin provides the ability to import and export challenges in a portable, human-readable format (currently YAML, with JSON if there is popular demand). 

### Objectives:
* Allow challenges to be saved outside of the database
* Allow for source control on challenges
* Allow for easy human editing of challenges offline
* Enable rapid deployment of challenges to a CTFd instance

### Installation:
Simple clone this repository into the plugins folder of your CTFd deployment and start the server. This plugin will automatically be loaded.

### Usage:
You can use this plugin through the web API with a front-end at the '/admin/transfer' endpoint, or through the CLI

#### Web endpoints:
There are two endpoints which are associated with this plugin. 

* '/admin/yaml': This is where the file transfer takes place. It supports two methods.
  * `GET`: Will send, as an attachment, a compressed tarball archive containing all of the currently configured challenges and their files
  * `POST`: Requires a tarball archive, optional compressed with gzip or bz2, to be attached in the 'file' field. This will unpack the archive and add any challenges which are not already in the database. The archive should contain the challenge spec as 'export.yaml' at the root directory of the archive, and no paths should reach into directories above the archive (e.g. ../../etc/passwd would trigger an error) A challenge is not added if it is an exact replica of an existing challenge including name, category, files, keys, etc...

* '/admin/transfer': This is the front-end for the import/export system. It provides a simple interface by which the endpoint described above can be accessed

#### Command line interface:
The `importer.py` and `exporter.py` scripts can be called directly from the CLI. This is much preferred if the archive you are uploading/downloading is saved on the server because it will not need to use the network.

The help dialog follows:
```
usage: importer.py [-h] [--app-root APP_ROOT] [-d DB_URI] [-F DST_ATTACHMENTS] [-i IN_FILE] [--skip-on-error] [--move]

Import CTFd challenges and their attachments to a DB from a YAML formated
specification file and an associated attachment directory

optional arguments:
  -h, --help           show this help message and exit
  --app-root APP_ROOT  app_root directory for the CTFd Flask app (default: 2 directories up from this script)
  -d DB_URI            URI of the database where the challenges should be stored
  -F DST_ATTACHMENTS   directory where challenge attachment files should be stored
  -i IN_FILE           name of the input YAML file (default: export.yaml)
  --skip-on-error      If set, the importer will skip the importing challenges which have errors rather than halt.
  --move               if set the import proccess will move files rather than copy them

```
```
usage: exporter.py [-h] [--app-root APP_ROOT] [-d DB_URI] [-F SRC_ATTACHMENTS] [-o OUT_FILE] [-O DST_ATTACHMENTS] [--tar] [--gz] [--visible-only] [--remove-flags]

Export a DB full of CTFd challenges and theirs attachments into a portable
YAML formated specification file and an associated attachment directory

optional arguments:
  -h, --help           show this help message and exit
  --app-root APP_ROOT  app_root directory for the CTFd Flask app (default: 2 directories up from this script)
  -d DB_URI            URI of the database where the challenges are stored
  -F SRC_ATTACHMENTS   directory where challenge attachment files are stored
  -o OUT_FILE          name of the output YAML file (default: export.yaml)
  -O DST_ATTACHMENTS   directory for output challenge attachments (default: [OUT_FILENAME].d)
  --tar                if present, output to tar file
  --gz                 if present, compress the tar file (only used if '--tar'is on)
  --visible-only       if present, ignore hidden challenges
  --remove-flags       if present, replace flags with a placeholder
```

#### YAML Specification:

Each challenge is a single document. Multiple documents can be present in one YAML file, separated by “---”, as specified by YAML 1.1. 
 
Following is a list of top level keys with their usage.

**name**
* Type: Single line text
* Usage: Specify the title which will appear to the user at the top of the challenge and on the challenge page

**category**
* Type: Single line text
* Usage: Specify the category the challenge will appear a part of

**description**
* Type: Multiline text
* Usage: The the body text of the challenge. If HTML tags are used, they will be rendered.

**tags** (optional)
* Type: List of single line text items
* Usage: Specify searchable tags that indicate attributes of this challenge
* Default: Empty list

**value** 
* Type: Positive integer
* Usage: The amount of point awarded for completion of the problem

**type** (optional)
* Type: Single line text (standard | dynamic | naumachia)
* Usage: Specify the type of the challenge. Default: standard

**initial** (optional)
* Type: Positive integer
* Usage: (dynamic challenge only) This is how many points the challenge was worth initially. Defaults to `value` if not set.

**decay** (optional)
* Type: Positive integer
* Usage: (dynamic challenge only) The amount of solves before the challenge reaches its minimum value

**minimum** (optional)
* Type: Positive integer
* Usage: (dynamic challenge only) This is the lowest that the challenge can be worth

**naumachia_name** (optional)
* Type: Single line of text
* Usage: (naumachia challenge only) Used in conjuction with the [ctfd-naumachia-plugin]. Name of the associated challenge in Naumachia

[ctfd-naumachia-plugin]: https://github.com/nategraf/ctfd-naumachia-plugin

**files** (optional)
* Type: List of file paths (single line text)
* Usage: Specify paths to static files which should be included in challenge. On import these files will be uploaded. The filenames will remain the same on upload put the directories in the path will be replaced with a single directory with a random hexadecimal name. The file paths should be relative to the YAML file by default, but this can be changed by using command line arguments with the import tool.
* Default: Empty list

**flags**
* Type: List of flag objects
  
  **flag**
  * Type: Single line text
  * Usage: The flag/key text

  **type** (optional)
  * Type: Enum {REGEX, PLAINTEXT}
  * Usage: Specify whether the text should be compared to what the user enters directly, or as a regular expression
  * Default: PLAINTEXT

  **data** (optional)
  * Type: Enum {PLAINTEXT}
  * Usage: Specify whether the flag should be case sensitive or not. Possible values '' or case_insensitive
  * Default: ""

**hints** (optional)
* Type: List of hint objects
  
  **hint**
  * Type: Single line text
  * Usage: The hint text

  **type** (optional)
  * Type: Enum {REGEX, STANDARD}
  * Usage: Specify whether the text should be compared to what the user enters directly, or as a regular expression
  * Default: STANDARD
  
  **cost** (optional)
  * Type: Positive integer
  * Usage: The amount of point needed for revealing the hint
  * Default: 0

**hidden** (optional)
* Type: Boolean {true, false}
* Usage: Set to true if this challenge should not display to the user
* Default: false

**max_attempts** (optional)
* Type: Positive integer
* Usage: Maximum amount of attempts users receive. Leave at 0 for unlimited.
* Default: 0

**requirements** (optional)
* Type: List of single line text items
* Usage: Enumerate the names of challenges that are required by this challenge
* Default: Empty

##### Example YAML File

```YAML
---
category: tristique
description: Aenean nulla dolor, imperdiet id massa eu, iaculis mattis urna. Nullam
  commodo velit nec tellus egestas, quis varius nulla malesuada. Orci varius natoque
  penatibus et magnis dis parturient montes, nascetur ridiculus mus. Morbi dapibus
  lorem non tristique placerat. Lorem ipsum dolor sit amet, consectetur adipiscing
  elit.
files:
- export.d/8f227f1c7f305b3fcd39cc06d54a7e36/bfn1o8t5s6dy.gif
- export.d/4ab77d38dd646bb81e8d6d2533eec71c/bPXFXW7.mp4
flags:
- flag: pharetra
  data: case_insensitive
name: Duis
value: 10
hints:
- hint: 'Hint: Buda huba cupa? nulla musca'
  type: standard
  cost: 2
---
category: netus
description: Duis nibh elit, ultricies non erat non, vulputate vestibulum risus. Nullam
  posuere ac nisi vitae lobortis. Vivamus convallis dictum nunc sed cursus.
files:
- export.d/1e9f731e310179959337a26307356513/LYVIZ4x.mp4
flags:
- flag: ante
  data: ''
hidden: true
name: Integer
value: 30
type: dynamic
initial: 300
decay: 10
minimum: 1
---
category: tristique
description: Praesent ullamcorper orci condimentum sapien tincidunt lacinia. Pellentesque
  habitant morbi tristique senectus et netus et malesuada fames ac turpis egestas.
  Suspendisse sem elit, euismod nec orci sit amet, elementum pulvinar ligula. Pellentesque
  sed mi leo. Nam vulputate, massa at porta condimentum, odio nulla dictum sem, vel
  rhoncus turpis quam at odio. Nam pharetra faucibus augue a rhoncus. In hac habitasse
  platea dictumst.
files:
- export.d/479922c8a73612596ba64c681aa8a022/21KNq7T.mp4
flags:
- flag: orci
name: suscipit nisi eget
value: 40
---
category: tristique
description: Praesent ullamcorper orci condimentum sapien tincidunt lacinia. Pellentesque
  habitant morbi tristique senectus et netus et malesuada fames ac turpis egestas.
files:
- export.d/8d25765f0902bfc03634e2f578e75e16/ES5hMrK.mp4
- export.d/6a1586bced5fbed05ec64392dca6b0f1/fAiFGB3.mp4
flags:
- flag: '[eaEA]gesta(s)+'
- flag: habitant
- flag: turpis
- flag: nisi
name: Pellentesque
value: 40
type: standard
---
category: Test
description: Tset
files:
- export.d/ad752f7af75045c1e6735148af09075f/bridge-up.sh
flags:
- flag: key
name: Test
value: 50
---
category: imperdiet
description: Aenean nulla dolor, imperdiet id massa eu, iaculis mattis urna. Nullam
  commodo velit nec tellus egestas, quis varius nulla malesuada. Orci varius natoque
  penatibus et magnis dis parturient montes, nascetur ridiculus mus. Morbi dapibus
  lorem non tristique placerat. Lorem ipsum dolor sit amet, consectetur adipiscing
  elit. Cras ac orci lacinia, tempus purus et, pharetra neque. Nullam facilisis sed
  purus vel pharetra. Donec nec pulvinar massa.
flags:
- flag: Maecenas
name: Cras
value: 90
```
### Development 

You can test the plugin with the latest CTFd using Docker Compose. 

The CTFd version can be modified in the `Dockerfile`. 

```angular2html
FROM ctfd/ctfd:3.7.3
```

Run the following command from the source repository to start CTFd with the plugin enabled:

```bash
docker-compose up
```

Now you can edit the source code, and the changes will be reflected in the container.  
Have you found a bug? It should be easy to fix it and to submit a pull request! 
