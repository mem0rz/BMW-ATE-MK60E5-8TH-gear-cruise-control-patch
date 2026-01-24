At your own risk!At your own risk!At your own risk!At your own risk!At your own risk!At your own risk!
This modification is a security-level change, and you assume full responsibility for it. The project bears no liability whatsoever. Any consequences arising from the use of this project shall be borne solely by the user.

Fix a DSC firmware issue where  cruise control drops out in 8th gear, and reduce/avoid the related  ISTA history DTC 5E62, while keeping changes minimal and low-risk (especially preserving brake/cancel safety exits). 
1) Firmware Loading (confirmed) 

    Image file:  6862873A111.bin (16 MB), but valid ROM image starts at  file offset 0x3AC. 
    ROM mapping: 
        ROM base  0x00400000, ROM size  0x00100000
    Verified address conversion: 
        file_off = (EA - 0x00400000) + 0x3AC
    IDA settings: PPC/MPC55xx, Big Endian, VLE enabled. 

2) Key Discovery: Most DSC logic is a 16‑bit Token VM (script/bytecode) 

Instead of native PPC instructions, large parts are a structured 16‑bit token stream: 

    A7xx: read slot/variable 
    B7xx: case/compare branch on the last-read value 
    00CF: end/return marker 
    25F0 xxxx: strongly correlated with CAN/context-driven signal extraction 

Analysis therefore focuses on token flow segmentation, branch paths, and slot read/write chains. 
3) Root Symptom in Cruise Logic:  slot0C == 0x0B causes immediate exit 

In the cruise-related VM block ( 0x004DA3AC): 

    A70C reads  slot[0x0C]
    B70B is followed by a short  FAST_EXIT sequence ( ... 21F0 00CF), i.e., immediate return. 
    The cruise switch compares only  0x0B and  0x0C (not a “>=8 gears” range check). 

A global “last A7 == 0x0C” filter reduced noise and confirmed only a small number of true  slot0C==0x0B comparisons across the ROM, with cruise being the only one that exits immediately. 
4) Upstream Source:  slot0C comes from transmission/CAN context and is re-processed 

A unique signature located the main landing point for  slot0C: 

    Only one place contains the pattern  9720; 970C (same value stored into two slots), at  0x4541BC. 
    Immediately before it, the VM executes: 
        25F0 0078
        25F0 7CE0
        then stores to  slot20 and  slot0C
        This indicates a context/signal extraction step feeding the value. 

Further investigation showed  multiple writers to  slot0C (not just the raw decode path), including a  ctx=0079 “sanitizing/gating” path ( 0x492A96) that conditionally skips writing  slot0C/ slot0B based on threshold checks (e.g.,  8C0B plus conditional jumps). This supports the idea that 0x0B is treated as a boundary/unsupported code in some flows. 
5) ISTA DTC Link: 5E62 is mapped to internal monitor ID 0x202A and that monitor uses 0x0B as a boundary 

    A diagnostic mapping table in ROM contains: 
        202A → 5E62
    Non-table uses of  202A were found at only a few locations. 
    In the  ctx=0079 monitor block containing  202A ( 0x4C59C8..0x4C5BD2), explicit boundary tokens appear: 
        A90B and  B90B (clear “0x0B boundary” indicators) 
        This provides a static explanation for “8th gear triggers a history DTC”: 0x0B is not only a cruise-exit code path, it is also referenced as a diagnostic boundary in a monitor that maps to 5E62. 

6) Patch Design (minimal, no new cases inserted) 
Principles 

    Avoid inserting new VM cases/tokens (high risk). 
    Prefer changing existing 16-bit constants/tokens (low-risk, reversible). 
    Address both: (a) the DTC boundary and (b) cruise drop-out behavior. 

Patch set 

     DTC 202A / 5E62 boundary shift

    A90B → A90C
    B90B → B90C
    This moves the monitor’s “0x0B boundary” to 0x0C, reducing the chance that 8th gear (often encoded as 0x0B) triggers the monitor. 

     Cruise behavior fix (swap cases)

    Swap  B70B and  B70C in the cruise switch: 
        B70C → B70B
        B70B → B70C
        This prevents  slot0C==0x0B from taking the FAST_EXIT branch, without adding new cases. 

Patches were implemented at the Intel HEX ( .0pa) level for WinkFP flashing, with automatic recomputation of Intel HEX line checksums. 
