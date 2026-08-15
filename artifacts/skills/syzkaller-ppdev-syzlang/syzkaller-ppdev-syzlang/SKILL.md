---
name: syzkaller-ppdev-syzlang
description: >
  Write syzkaller syzlang system call descriptions for the Linux ppdev
  (parallel port) driver. Use when creating .txt and .txt.const files
  for fuzzing /dev/parportN devices, describing ppdev ioctls, resources,
  structs, flags, and computing ioctl command numbers.
---

# Syzkaller Syzlang Descriptions for ppdev

This skill produces two files for the syzkaller kernel fuzzer:
1. A `.txt` syzlang description file for the ppdev driver
2. A `.txt.const` constants file with architecture-specific numeric values

## File Structure

The `.txt` file follows this order:
1. Include directives
2. Resource declarations
3. Device open call
4. Ioctl descriptions
5. Struct definitions
6. Flag definitions

## Include Directives

Start with the kernel headers that define ppdev and parport constants:

```
include <linux/ppdev.h>
include <linux/parport.h>
```

## Resource Declaration

Declare a file descriptor resource for ppdev devices:

```
resource fd_ppdev[fd]
```

## Device Opening

Use `syz_open_dev` with the parport device path template. The `#` is replaced by syzkaller with small integers during fuzzing:

```
syz_open_dev$ppdev(dev ptr[in, string["/dev/parport#"]], id intptr, flags flags[open_flags]) fd_ppdev
```

## Ioctl Descriptions

Each ioctl specializes the generic `ioctl` syscall with a `$NAME` suffix.

### No-data ioctls (use `_IO` encoding)

These take exactly two parameters - fd and command constant. No third argument:

```
ioctl$PPCLAIM(fd fd_ppdev, cmd const[PPCLAIM])
ioctl$PPRELEASE(fd fd_ppdev, cmd const[PPRELEASE])
ioctl$PPYIELD(fd fd_ppdev, cmd const[PPYIELD])
ioctl$PPEXCL(fd fd_ppdev, cmd const[PPEXCL])
```

### Data-transferring ioctls

These add a third `ptr[direction, type]` argument.

Direction mapping (this is critical to get right):
- `_IOW` (user writes TO kernel) → `ptr[in, ...]`
- `_IOR` (kernel reads OUT to user) → `ptr[out, ...]`

**Mode management (4-byte int):**

```
ioctl$PPSETMODE(fd fd_ppdev, cmd const[PPSETMODE], arg ptr[in, flags[ieee1284_modes, int32]])
ioctl$PPGETMODE(fd fd_ppdev, cmd const[PPGETMODE], arg ptr[out, int32])
ioctl$PPGETMODES(fd fd_ppdev, cmd const[PPGETMODES], arg ptr[out, int32])
ioctl$PPNEGOT(fd fd_ppdev, cmd const[PPNEGOT], arg ptr[in, flags[ieee1284_modes, int32]])
```

**Data transfer (1-byte):**

```
ioctl$PPRDATA(fd fd_ppdev, cmd const[PPRDATA], arg ptr[out, int8])
ioctl$PPWDATA(fd fd_ppdev, cmd const[PPWDATA], arg ptr[in, int8])
ioctl$PPDATADIR(fd fd_ppdev, cmd const[PPDATADIR], arg ptr[in, int32])
```

**Status and control:**

```
ioctl$PPRSTATUS(fd fd_ppdev, cmd const[PPRSTATUS], arg ptr[out, int8])
ioctl$PPRCONTROL(fd fd_ppdev, cmd const[PPRCONTROL], arg ptr[out, int8])
ioctl$PPWCONTROL(fd fd_ppdev, cmd const[PPWCONTROL], arg ptr[in, int8])
ioctl$PPFCONTROL(fd fd_ppdev, cmd const[PPFCONTROL], arg ptr[in, ppdev_frob_struct])
ioctl$PPWCTLONIRQ(fd fd_ppdev, cmd const[PPWCTLONIRQ], arg ptr[in, int8])
```

**IRQ and timing:**

```
ioctl$PPCLRIRQ(fd fd_ppdev, cmd const[PPCLRIRQ], arg ptr[out, int32])
ioctl$PPGETTIME(fd fd_ppdev, cmd const[PPGETTIME], arg ptr[out, timeval])
ioctl$PPSETTIME(fd fd_ppdev, cmd const[PPSETTIME], arg ptr[in, timeval])
```

**Flags and phase (4-byte int):**

```
ioctl$PPGETFLAGS(fd fd_ppdev, cmd const[PPGETFLAGS], arg ptr[out, int32])
ioctl$PPSETFLAGS(fd fd_ppdev, cmd const[PPSETFLAGS], arg ptr[in, flags[ppdev_flags, int32]])
ioctl$PPGETPHASE(fd fd_ppdev, cmd const[PPGETPHASE], arg ptr[out, int32])
ioctl$PPSETPHASE(fd fd_ppdev, cmd const[PPSETPHASE], arg ptr[in, int32])
```

## Struct Definitions

```
ppdev_frob_struct {
	mask	int8
	val	int8
}
```

The frob struct is exactly 2 bytes (two unsigned char fields). Using wrong sizes changes the ioctl number.

## Flag Definitions

```
ieee1284_modes = IEEE1284_MODE_NIBBLE, IEEE1284_MODE_BYTE, IEEE1284_MODE_COMPAT, IEEE1284_MODE_ECP, IEEE1284_MODE_ECPRLE, IEEE1284_MODE_ECPSWE, IEEE1284_MODE_EPP, IEEE1284_MODE_EPPSWE, IEEE1284_DEVICEID, IEEE1284_EXT_LINK
ppdev_flags = PP_FASTWRITE, PP_FASTREAD, PP_W91284PIC
```

## Computing Ioctl Numbers for .txt.const

All ppdev ioctls use type character `'p'` (ASCII 0x70 = 112).

### Encoding formula

| Macro | Formula |
|-------|--------|
| `_IO(type, nr)` | `(type << 8) \| nr` |
| `_IOR(type, nr, size)` | `0x80000000 \| (size << 16) \| (type << 8) \| nr` |
| `_IOW(type, nr, size)` | `0x40000000 \| (size << 16) \| (type << 8) \| nr` |

Data type sizes: int=4, char/unsigned char=1, ppdev_frob_struct=2, timeval=16 (on 64-bit)

### Example: PPSETMODE = _IOW('p', 0x80, int)

`0x40000000 | (4 << 16) | (0x70 << 8) | 0x80 = 0x40047080 = 1074032768`

## Constants File Format

The `.txt.const` file must:
- Start with `arches = amd64, 386` (or appropriate architectures)
- List every symbolic constant from the .txt file
- Use **decimal** values (not hex)
- Include ioctl command numbers, flag values, and all other constants

A missing constant causes `syz-sysgen` compilation failure.

## Common Pitfalls

1. **Direction confusion**: `_IOR` → `ptr[out, ...]`, `_IOW` → `ptr[in, ...]`. The R/W is from kernel perspective.
2. **Wrong data sizes**: Each ioctl encodes its argument size. int=4 bytes, char=1 byte, frob=2 bytes, timeval=16 bytes.
3. **Hex in const file**: Values must be decimal. `0x40047080` is wrong; `1074032768` is correct.
4. **Missing arches line**: The const file needs `arches = amd64, 386`.
5. **No-data ioctls with extra args**: `_IO` ioctls (PPCLAIM, PPRELEASE, PPYIELD, PPEXCL) must NOT have a third pointer argument.
6. **Missing constants**: Every symbol in .txt needs an entry in .txt.const.
