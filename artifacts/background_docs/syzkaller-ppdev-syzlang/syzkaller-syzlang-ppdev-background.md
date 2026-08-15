# Syzkaller Syzlang Descriptions for the Linux ppdev Driver

This document provides background on writing syzkaller system call descriptions (syzlang) for the Linux parallel port user-space device driver (`ppdev`), covering the syzlang grammar, the Linux ioctl encoding scheme, the ppdev subsystem's architecture, and the constant file format.

## Syzkaller and Syzlang Overview

Syzkaller is a coverage-guided kernel fuzzer for Linux (and other OSes). It generates sequences of system calls to exercise kernel code paths and find bugs. To fuzz effectively, syzkaller needs structured descriptions of each system call interface so that it can produce syntactically valid arguments rather than random bytes.

These descriptions are written in **syzlang**, a domain-specific language stored in `.txt` files under `sys/linux/` in the syzkaller source tree. Each `.txt` file describes the syscall surface for a particular subsystem or driver. A companion `.txt.const` file provides architecture-specific numeric values for the symbolic constants referenced in the description file.

The syzkaller build pipeline works in two stages:

1. **`make descriptions`** compiles `.txt` + `.txt.const` files into Go source code using the `syz-sysgen` tool.
2. **`make all`** builds the full syzkaller binary suite (including `syz-fuzzer`, `syz-executor`, `syz-manager`) incorporating the generated descriptions.

Both stages must succeed without errors for a description to be valid.

## Syzlang Grammar Essentials

### Includes

Syzlang files begin with `include` directives that reference Linux UAPI headers. These tell `syz-sysgen` which kernel headers define the constants used in the description:

For example, `include <linux/ppdev.h>` and `include <linux/parport.h>` reference the kernel headers that define the ppdev and parport constants.

### Resources

A **resource** is a typed wrapper around a base type that tracks kernel object lifetimes across system calls. The most common pattern is wrapping file descriptors so that syzkaller knows which fd values were produced by an open call and can reuse them in subsequent ioctl calls:

For example, `resource fd_ppdev[fd]` declares `fd_ppdev` as a subtype of `fd`.

This declares `fd_ppdev` as a subtype of `fd`. Any syscall that returns `fd_ppdev` produces values that can flow into parameters typed as `fd_ppdev`.

### Device Opening with syz_open_dev

Syzkaller provides the pseudo-syscall `syz_open_dev` for opening device files whose names contain a numeric index. The `#` character in the path string is a placeholder that syzkaller replaces with small integers during fuzzing:

For example: `syz_open_dev$variant(dev ptr[in, string["/dev/parport#"]], id intptr, flags flags[open_flags]) fd_ppdev`.

Key elements:
- **`$variant`** is a specialization suffix that distinguishes this open call from others (e.g., `$ppdev`).
- The first argument is a pointer to an input string containing the device path template.
- The return type must be the resource type (e.g., `fd_ppdev`) so syzkaller can feed the resulting fd into subsequent ioctls.

### Ioctl Descriptions

Ioctls are described by specializing the generic `ioctl` syscall with a `$NAME` suffix. Every ioctl description takes at minimum the file descriptor and a command constant. Data-transferring ioctls add a third pointer argument:

**No-data ioctls** (encoded with `_IO` in the kernel) have exactly two parameters: the fd and the command constant. For example, an ioctl like PPCLAIM has no third argument -- just the file descriptor and the command constant.

**Data-transferring ioctls** (encoded with `_IOR` or `_IOW`) add a third pointer argument. For write-to-kernel ioctls like PPSETMODE, the pointer direction is `in` with the appropriate data type. For read-from-kernel ioctls like PPGETMODE, the pointer direction is `out` with the appropriate data type.

The `ptr[direction, type]` wrapper specifies:
- **`in`** for `_IOW` ioctls (user writes data to the kernel)
- **`out`** for `_IOR` ioctls (kernel writes data to the user)

The pointer direction corresponds to the **data flow direction from the user-space perspective**, which is the opposite of what the `R`/`W` in the macro name might suggest: `_IOR` means the kernel reads-out to user-space (direction is `out`), and `_IOW` means the kernel writes-in from user-space (direction is `in`).

### Structs

Syzlang structs mirror C structs. Fields are listed one per line inside braces, with the field name followed by its type:

For example, `ppdev_frob_struct` is declared with two fields listed one per line inside braces: `mask` of type `int8` and `val` of type `int8`.

Field types must match the actual sizes of the corresponding C struct members.

### Flags

Named flag sets group related constants for use in typed ioctl arguments:

For example, `ieee1284_modes = IEEE1284_MODE_NIBBLE, IEEE1284_MODE_BYTE, IEEE1284_MODE_ECP, ...` groups the IEEE 1284 mode constants, and `ppdev_flags = PP_FASTWRITE, PP_FASTREAD, PP_W91284PIC` groups the ppdev-specific flag constants.

An ioctl argument can reference a flag set via `flags[flag_set_name, base_type]`, which tells syzkaller to generate values by ORing together members of that set.

## Linux ioctl Number Encoding

Linux encodes ioctl command numbers into 32-bit integers using four fields. Understanding this encoding is essential for computing the numeric values that go into the `.txt.const` file.

### Bit Layout

| Bit Range | Field | Description |
|---|---|---|
| 31-30 | Direction | 00 = none, 01 = write, 10 = read, 11 = read+write |
| 29-16 | Size | Size of the argument data in bytes |
| 15-8 | Type | Magic number identifying the driver, usually an ASCII character |
| 7-0 | Nr | Command number within the driver |

### Encoding Macros

The kernel provides four macros (defined in `<asm/ioctl.h>`):

- **`_IO(type, nr)`** -- no data transfer. Direction bits are 0, size is 0.
  - Result: `(type << 8) | nr`

- **`_IOR(type, nr, datatype)`** -- kernel writes to user-space (read direction).
  - Direction = `0x80000000` (bit 31 set)
  - Result: `0x80000000 | (sizeof(datatype) << 16) | (type << 8) | nr`

- **`_IOW(type, nr, datatype)`** -- user-space writes to kernel (write direction).
  - Direction = `0x40000000` (bit 30 set)
  - Result: `0x40000000 | (sizeof(datatype) << 16) | (type << 8) | nr`

- **`_IOWR(type, nr, datatype)`** -- bidirectional transfer.
  - Direction = `0xC0000000` (bits 30-31 set)
  - Result: `0xC0000000 | (sizeof(datatype) << 16) | (type << 8) | nr`

### ppdev Type Character

All ppdev ioctls use the type character `'p'`, whose ASCII value is `0x70` (112 decimal). This means every ppdev ioctl has `0x70` in bits 15-8.

### Size Field

The size field encodes the byte size of the C data type passed to the ioctl:
- `int` = 4 bytes
- `char` / `unsigned char` = 1 byte
- `struct ppdev_frob_struct` = 2 bytes (two `unsigned char` fields)
- `struct timeval` = 16 bytes (on 64-bit: two `long` fields of 8 bytes each)

Getting the size wrong by even one byte produces a completely different ioctl number.

### Worked Example

For `PPSETMODE`, defined in the kernel as `_IOW('p', 0x80, int)`:

1. Direction: `_IOW` = `0x40000000`
2. Size: `sizeof(int)` = 4, shifted left 16 = `0x00040000`
3. Type: `'p'` = 0x70, shifted left 8 = `0x00007000`
4. Nr: `0x80`
5. Combined: `0x40000000 | 0x00040000 | 0x00007000 | 0x80` = `0x40047080`

In decimal, this is `1074032768`.

## The ppdev Subsystem

### Purpose and Architecture

The ppdev (parallel port device) driver provides user-space access to IEEE 1284 parallel ports via `/dev/parport0`, `/dev/parport1`, etc. It is a character device driver that exposes parallel port functionality entirely through `open()`, `close()`, `read()`, `write()`, and `ioctl()` system calls.

The driver sits on top of the `parport` subsystem, which manages the physical parallel port hardware. The ppdev layer adds an access-control model (claim/release) that allows multiple user-space processes to share a single parallel port.

### Ioctl Categories

The 23 ppdev ioctls fall into distinct functional groups:

**Port Access Control (no data argument):**
These ioctls manage exclusive access to the parallel port. A process must claim the port before performing I/O and should release it when done. They use `_IO()` encoding (no data transfer):
- Claim the port for exclusive use
- Release the port
- Yield the port temporarily to other waiters
- Request exclusive (non-sharing) access

**Mode Management (4-byte int argument):**
Parallel ports support multiple communication modes defined by the IEEE 1284 standard. These ioctls set or query the current operating mode, query which modes the hardware supports, and negotiate a mode with the attached peripheral:
- Set operating mode (`_IOW`, direction `in`)
- Get current mode (`_IOR`, direction `out`)
- Get supported modes (`_IOR`, direction `out`)
- Negotiate mode with device (`_IOW`, direction `in`, uses mode flags)

**Data Transfer (1-byte argument):**
Direct register-level access for reading/writing the data port and setting data direction:
- Read data register (`_IOR`, direction `out`, 1-byte)
- Write data register (`_IOW`, direction `in`, 1-byte)
- Set data direction (`_IOW`, direction `in`, 4-byte int)

**Status and Control (1-byte argument):**
Read status lines, read/write control lines, and atomically frob (modify) control bits:
- Read status register (`_IOR`, direction `out`, 1-byte)
- Read control register (`_IOR`, direction `out`, 1-byte)
- Write control register (`_IOW`, direction `in`, 1-byte)
- Frob control register (`_IOW`, direction `in`, uses the frob struct)
- Set control lines to assert on IRQ (`_IOW`, direction `in`, 1-byte)

**IRQ and Timing:**
- Clear IRQ count (`_IOR`, direction `out`, 4-byte int)
- Get/set timeout as a `timeval` structure (`_IOR`/`_IOW`, 16 bytes on 64-bit)

**Flags and Phase (4-byte int argument):**
- Get/set ppdev-specific flags (`_IOR`/`_IOW`)
- Get/set IEEE 1284 negotiation phase (`_IOR`/`_IOW`)

### The Frob Struct

The "frob" operation (from "FRacture Or Bitwise" -- a kernel idiom for masked bit modification) atomically modifies control register bits. The struct contains two single-byte fields:
- **mask**: which bits to modify
- **val**: what values to set for those bits

The kernel applies: `new_control = (old_control & ~mask) | (val & mask)`. Because both fields are `unsigned char` (1 byte each), the struct is 2 bytes total.

### IEEE 1284 Mode Flags

The IEEE 1284 standard defines several parallel port communication modes. Each mode is represented by a flag bit (or combination of bits) that can be ORed together. The modes defined in `<linux/parport.h>` include:

- **Nibble mode** (baseline, value 0) -- 4-bit reverse channel
- **Byte mode** -- 8-bit reverse channel
- **Compatibility mode** -- standard forward-only (Centronics)
- **ECP** (Extended Capability Port) -- high-speed bidirectional with hardware FIFO
- **ECP+RLE** -- ECP with run-length encoding
- **ECP+software** -- software-emulated ECP
- **EPP** (Enhanced Parallel Port) -- high-speed bidirectional register-mapped
- **EPP+software** -- software-emulated EPP

Additional flags exist for device ID retrieval, extended link negotiation, and distinguishing address vs. data cycles.

### ppdev-Specific Flags

The ppdev driver defines its own flags that control driver behavior:
- **Fast write** -- use optimized (DMA/FIFO) write path
- **Fast read** -- use optimized read path
- **W91284PIC** -- Warp9 IEEE 1284 PIC mode

These flags are set/queried via the flags ioctls and should be declared as a flag set in syzlang so syzkaller can generate valid combinations.

## The Constants File Format

Each syzlang `.txt` file requires a companion `.txt.const` file that maps symbolic names to their numeric values. This file is architecture-specific because ioctl numbers can differ between architectures (due to different type sizes).

### Structure

The file begins with an optional comment line (starting with `#`), followed by an `arches` declaration (e.g., `arches = amd64, 386`), then one line per constant in the form `CONSTANT_NAME = decimal_value`.

Key rules:
- The `arches` line declares which architectures these values apply to. For x86 systems, `amd64, 386` covers both 64-bit and 32-bit.
- Every symbolic constant referenced in the `.txt` file must have a corresponding entry in the `.txt.const` file.
- Values are in **decimal** (not hexadecimal).
- The file must contain entries for all ioctl command numbers, all flag values, and any other numeric constants used in the descriptions.

### What to Include

A complete constants file for a device driver typically contains:
1. **Ioctl command numbers** -- computed via the encoding macros described above
2. **Flag values** -- the numeric values of each flag constant
3. **Any other symbolic constants** referenced in the `.txt` file

If a constant is referenced in the `.txt` file but missing from `.txt.const`, the `syz-sysgen` compilation step will fail.

## Key Distinctions in Practice

**The `_IOR`/`_IOW` naming convention reflects the kernel's perspective, while syzlang pointer directions reflect the user-space perspective.** Specifically, `_IOR` means the kernel reads data out to user-space, so the syzlang direction is `out`; `_IOW` means user-space writes data in to the kernel, so the syzlang direction is `in`. These two naming conventions are complementary rather than contradictory, but maintaining clarity about which perspective is in use is essential for correct descriptions.

**Each ioctl number embeds the exact byte size of its data argument.** The ppdev driver uses a mix of 1-byte, 2-byte, 4-byte, and 16-byte arguments across its ioctls. Using the wrong size (for example, 4 bytes when the actual argument is 1 byte, or vice versa) produces a completely different ioctl number, because the size occupies bits 29-16 of the encoded value.

**No-data ioctls encoded with `_IO()` take exactly two syzlang parameters: the file descriptor and the command constant.** These ioctls have no direction bits and no size field. The four ppdev port-access-control ioctls all use `_IO()` encoding and have no pointer argument in their syzlang descriptions.

**Every symbolic name referenced in the `.txt` file must have a corresponding entry in the `.txt.const` file.** This includes not just the ioctl command names but also all members of flag sets and any other named constants. A missing entry causes the syz-sysgen compilation step to fail during the build process.

**The constants file uses decimal integer values.** Writing hexadecimal notation (e.g., 0x40047080) instead of the equivalent decimal value (1074032768) will cause parsing errors in the syz-sysgen tool.

**The `arches` declaration is required in the constants file.** This line specifies which architectures the constant values apply to. Without it, the build tooling does not know which architectures the constants cover and may silently skip the file or produce build errors.

**The struct timeval has architecture-dependent size.** On 64-bit Linux, `struct timeval` contains two `long` fields (8 bytes each), totaling 16 bytes. On 32-bit Linux, `long` is 4 bytes, making the struct 8 bytes total. Since ioctl numbers embed the struct size, timeval-based ioctls have different numeric values on different architectures. For amd64, the size is 16.

**The ppdev_frob_struct is exactly 2 bytes.** It contains two `unsigned char` fields (mask and val), each 1 byte. Using larger field types (such as 4-byte integers) would change the struct to a different total size and produce incorrect ioctl numbers for the frob control ioctl.
