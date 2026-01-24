At your own risk!At your own risk!At your own risk!At your own risk!At your own risk!At your own risk!
This modification is a security-level change, and you assume full responsibility for it. The project bears no liability whatsoever. Any consequences arising from the use of this project shall be borne solely by the user.

Fix a DSC firmware issue where  cruise control drops out in 8th gear, and reduce/avoid the related  ISTA history DTC 5E62, while keeping changes minimal and low-risk (especially preserving brake/cancel safety exits). 
1) Source: EGS CAN message 0x1D2 (“TransmissionDataDisplay”)

A community DBC indicates CAN ID 0x1D2 (decimal 466) is an EGS message carrying gear display/gear-related fields. In the DSC image we found a VM path strongly tied to a “context” handle 0x0078 and a signal handle 0x7CE0.
1.1 Direct decode / landing into slot0C

In the VM block starting at 0x4541AC:

    25F0 0078 selects a CAN/context buffer (context handle 0x0078).
    25F0 7CE0 selects a specific signal (signal handle 0x7CE0).
    Immediately after, the same current value is stored twice:
        9720 then 970C

This pattern (9720 970C back-to-back) appears only once in the entire ROM, and within the discovered 0x1D2 chain this is the only 970C store. That makes it the strongest candidate for “gear(ish) signal → slot0C” landing.

Empirically, in driving conditions where “8th gear causes cruise to drop”, the internal value being compared later is 0x0B, which matches a common “PRND + forward gear” enumeration scheme (e.g., 7th=0x0A, 8th=0x0B, 9th=0x0C).
2) Cruise logic: slot0C==0x0B triggers an immediate exit

In the cruise-related VM block (0x4DA3AC), the code reads slot0C and uses a case/branch:

    A70C read slot0C
    B70B case value 0x0B → executes a short “return/terminate” sequence (… 21F0 00CF), i.e. a fast exit.
    B70C case value 0x0C → follows a different path (not the fast-exit block).

So the cruise dropout is not a “>=8” range check; it is an exact match on slot0C == 0x0B.

A global scan confirms there are only 6 places in the ROM where slot0C is actually the active compare value and the case value is 0x0B. Only the cruise block uses that compare to do an immediate early return.
3) There is additional processing (ctx=0x0079) that gates slot0C updates

Besides the direct landing above, there is a separate VM block under context 0x0079 (starting 0x492A96) that conditionally updates slot0C (and also writes slot0B):

    It contains two independent “fail → skip stores → return” gates:
        Gate 1 uses 7D1C plus an explicit threshold constant 8C0B, then branches via E047 to a return path. This branch skips the 970C and 970B stores.
        Gate 2 uses 7C8F and branches via E020 to another return path, also skipping the stores.

When both gates pass, the block performs:

    970C (write slot0C)
    970B (write slot0B)

This is not a simple decode; it is a validation/normalization path. The presence of the explicit 0x0B threshold (8C0B) suggests the firmware treats the 0x0B boundary as special in this path as well (consistent with “7-gear expectation” vs “8-gear reality”).
4) DTC 5E62 is tied to monitor ID 0x202A, and monitor logic uses a 0x0B threshold

A DTC/monitor mapping table is present at 0x4E7080 with entries like:

    202A 5E62 ...

So DTC 5E62 corresponds to internal monitor ID 0x202A.

We found only three non-table uses of 0x202A, and one of them is a ctx=0x0079 block at 0x4C59C8..0x4C5BD2 which contains:

    25F0 0079 (ctx select)
    202A (monitor ID)
    explicit A90B and B90B compare/threshold tokens

That provides a plausible explanation for the field observation: when “8th gear” is present (encoded as 0x0B), the DSC not only drops cruise (slot0C==0x0B fast exit), but also has a monitor that treats 0x0B as a boundary and can log 5E62 as a history fault.
5) Patch approach used (minimal edits, no new cases)

Two patches were selected to avoid restructuring VM code:

     Suppress the 5E62-trigger boundary at 0x0B in the monitor block (ctx=0x0079, monitor 0x202A):

    A90B → A90C
    B90B → B90C

     Prevent cruise from immediately exiting on slot0C==0x0B without adding new cases:

    swap the cruise cases by changing the two tokens:
        B70C → B70B
        B70B → B70C
