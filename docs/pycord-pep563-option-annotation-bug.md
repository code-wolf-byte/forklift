# py-cord: `Option(...)` as Annotation Breaks Under `from __future__ import annotations`

**Affects:** py-cord up to and including v2.7.2 (latest as of 2026-04-14)  
**Status:** Unfixed upstream  
**Workaround:** Available (see below)

---

## Summary

When a file contains `from __future__ import annotations` (PEP 563), using `Option(...)` as a parameter annotation on a slash command causes a `TypeError` at invocation time:

```
TypeError: issubclass() arg 1 must be a class
```

## Root Cause

PEP 563 (`from __future__ import annotations`) changes Python's behaviour so that all annotations are stored as **strings** rather than being evaluated at definition time. For example:

```python
# What the developer writes:
user: Option(discord.Member, "Pick a member")

# What Python actually stores in __annotations__ under PEP 563:
"Option(discord.Member, 'Pick a member')"
```

py-cord's `_parse_options` (in `discord/commands/core.py`) reads annotations via `p_obj.annotation` directly — it never calls `typing.get_type_hints()`, so the string is never resolved back into the actual `Option` instance.

py-cord then constructs `Option("Option(discord.Member, 'Pick a member')")` — an `Option` whose `input_type` and `_raw_type` are set from that raw string. `SlashCommandOptionType.from_datatype()` accepts strings and maps any unrecognised string to `SlashCommandOptionType.string`, so the option registers without error.

The crash happens later, in `_invoke`, when the command is actually called:

```python
# discord/commands/core.py
elif issubclass(op._raw_type, Enum):   # <-- _raw_type is a string, not a class
```

`issubclass()` requires its first argument to be a class. Passing a string raises:

```
TypeError: issubclass() arg 1 must be a class
```

The full traceback seen in production:

```
File ".../discord/commands/core.py", line 138, in wrapped
    ret = await coro(arg)
File ".../discord/commands/core.py", line 1062, in _invoke
    elif issubclass(op._raw_type, Enum):
TypeError: issubclass() arg 1 must be a class

The above exception was the direct cause of the following exception:
discord.errors.ApplicationCommandInvokeError: Application Command raised an exception:
TypeError: issubclass() arg 1 must be a class
```

Note: the command registers successfully and the bot starts without any error — the crash only occurs when a user actually invokes the command.

## Affected Annotation Patterns

Any slash command parameter that uses `Option(...)` directly as the type annotation in a file with `from __future__ import annotations`:

```python
# All of these break under PEP 563:
user:   Option(discord.Member, "Pick a member")
role:   Option(discord.Role,   "Pick a role")
asurite: Option(str,           "Enter an ASURITE ID")
count:  Option(int,            "Enter a number")
```

## Workaround

Move `Option(...)` from the annotation to the **default value**. Default values are always evaluated eagerly, even under PEP 563, so py-cord receives the real `Option` instance via `p_obj.default`:

```python
# Before (broken under PEP 563):
async def get_member_email(
    self,
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, "Discord member to look up"),
) -> None: ...

# After (works correctly):
async def get_member_email(
    self,
    ctx: discord.ApplicationContext,
    user: discord.Member = Option(discord.Member, "Discord member to look up"),
) -> None: ...
```

For optional parameters:

```python
# Before:
member: Option(discord.Member, "Discord member to ban", required=False, default=None)

# After:
member: discord.Member = Option(discord.Member, "Discord member to ban", required=False, default=None)
```

This works because `_parse_options` checks `isinstance(p_obj.default, Option)` and, when true, uses that `Option` instance directly (skipping the broken annotation path entirely).

## Proper Upstream Fix

Replace the direct annotation read in `_parse_options` with `typing.get_type_hints()`:

```python
# Current (broken):
option = p_obj.annotation

# Fixed:
hints = typing.get_type_hints(self.callback, include_extras=True)
option = hints.get(p_name, inspect.Parameter.empty)
```

`get_type_hints()` evaluates string annotations in the correct namespace, resolving them back to their original types regardless of whether PEP 563 is active.

A lighter defensive fix (prevents the crash, does not fix incorrect option types):

```python
# In _invoke:
elif isinstance(op._raw_type, type) and issubclass(op._raw_type, Enum):
```

## This Project

All slash command parameters in `asu_discord/cogs/verification.py` that used `Option(...)` as annotations were updated to use the default-value pattern as the workaround. The file has `from __future__ import annotations` at line 1.

Affected commands: `/verify` (force-verify), `/unverify`, `/ban`, `/email`.
