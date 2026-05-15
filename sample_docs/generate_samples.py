"""
Generate synthetic messy legal sample documents for testing.

Creates 3 document types:
1. lease_agreement.pdf   — clean digital PDF (Tier 1 extraction)
2. eviction_notice.pdf   — simulated scanned/low-res (Tier 2 OCR)
3. handwritten_note.png  — handwritten note image (Tier 3 OCR)

Run: python sample_docs/generate_samples.py
"""

import os
import sys
import textwrap
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

OUTPUT_DIR = Path(__file__).parent


def create_lease_agreement():
    """Create a clean digital PDF lease agreement."""
    try:
        import fitz  # pymupdf

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)

        content = textwrap.dedent("""
            RESIDENTIAL LEASE AGREEMENT

            This Residential Lease Agreement ("Agreement") is entered into as of January 15, 2023,
            between:

            LANDLORD: Margaret A. Pearson
            Address: 1200 West 57th Street, Suite 400, New York, NY 10019

            TENANT: Daniel J. Ross
            Address: 742 Evergreen Terrace, Apt 3B, New York, NY 10028

            PROPERTY: The premises located at 742 Evergreen Terrace, Apt 3B, New York, NY 10028
            ("the Property").

            1. LEASE TERM
            The lease term shall commence on February 1, 2023, and shall terminate on
            January 31, 2024 ("the Lease Term"), unless sooner terminated pursuant to this Agreement.

            2. RENT
            Tenant agrees to pay Landlord the sum of $3,200.00 per month as rent for the Property.
            Rent is due and payable on the first (1st) day of each calendar month. Rent payments
            shall be made payable to Margaret A. Pearson and delivered to the address above.

            3. SECURITY DEPOSIT
            Upon execution of this Agreement, Tenant shall deposit with Landlord the sum of
            $6,400.00 as a security deposit. Said deposit shall be held by Landlord as security
            for faithful performance of all terms and conditions of this Agreement.

            4. DEFAULT
            If Tenant fails to pay rent when due, or fails to perform any other obligation under
            this Agreement, Landlord may serve written notice upon Tenant demanding performance.
            If Tenant fails to cure the default within three (3) days of receiving such notice,
            Landlord may elect to terminate this Agreement.

            5. PROPERTY CONDITION
            Tenant acknowledges that the Property is in good condition and agrees to maintain
            the Property in the same condition, ordinary wear and tear excepted.

            IN WITNESS WHEREOF, the parties have executed this Agreement as of the date first
            written above.

            ___________________________          ___________________________
            Margaret A. Pearson                  Daniel J. Ross
            Landlord                             Tenant

            Date: January 15, 2023               Date: January 15, 2023
        """).strip()

        page.insert_text(
            (50, 50),
            content,
            fontsize=11,
            fontname="helv",
            color=(0, 0, 0),
        )

        out_path = OUTPUT_DIR / "lease_agreement.pdf"
        doc.save(str(out_path))
        doc.close()
        print(f"Created: {out_path}")
        return out_path

    except ImportError:
        print("pymupdf not available — creating text fallback")
        out_path = OUTPUT_DIR / "lease_agreement.txt"
        out_path.write_text(content)
        return out_path


def create_eviction_notice():
    """Create a digital eviction notice PDF (simulating a notice to pay or quit)."""
    try:
        import fitz

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)

        content = textwrap.dedent("""
            NOTICE TO PAY RENT OR QUIT

            Date: March 8, 2025

            TO: Daniel J. Ross
                742 Evergreen Terrace, Apt 3B
                New York, NY 10028

            FROM: Margaret A. Pearson
                  1200 West 57th Street, Suite 400
                  New York, NY 10019

            NOTICE IS HEREBY GIVEN that you are in default under the terms of the Residential
            Lease Agreement dated January 15, 2023, for the premises located at 742 Evergreen
            Terrace, Apt 3B, New York, NY 10028.

            AMOUNT OF RENT DUE:
            - December 2024 rent:   $3,200.00  (due December 1, 2024 — UNPAID)
            - January 2025 rent:    $3,200.00  (due January 1, 2025 — UNPAID)
            - February 2025 rent:   $3,200.00  (due February 1, 2025 — UNPAID)
            - Late fees (3 months): $  480.00
            TOTAL AMOUNT DUE:       $10,080.00

            You are hereby required to pay the total amount due of $10,080.00 within THREE (3)
            DAYS of service of this notice, or to vacate and surrender possession of the above
            described premises.

            IF YOU FAIL TO PAY THE RENT OR VACATE THE PREMISES within the time specified above,
            legal proceedings will be instituted against you to recover possession of the premises,
            to declare the forfeiture of your lease, and to recover damages and costs of suit.

            Property Inspection Note: On February 15, 2025, a routine property inspection
            revealed significant damage to the kitchen cabinets and bathroom fixtures beyond
            normal wear and tear. Estimated repair cost: $2,100.00.

            This notice was served by:
            [ ] Personal delivery
            [ ] Posting on door + mailing
            [X] Certified mail (USPS Tracking: 9400111899223397889000)

            ___________________________
            Margaret A. Pearson
            Landlord / Authorized Agent
            March 8, 2025
        """).strip()

        page.insert_text(
            (50, 40),
            content,
            fontsize=10.5,
            fontname="helv",
            color=(0, 0, 0),
        )

        out_path = OUTPUT_DIR / "eviction_notice.pdf"
        doc.save(str(out_path))
        doc.close()
        print(f"Created: {out_path}")
        return out_path

    except ImportError:
        print("pymupdf not available — creating text fallback")
        out_path = OUTPUT_DIR / "eviction_notice.txt"
        out_path.write_text(content)
        return out_path


def create_property_inspection_note():
    """
    Create a simulated handwritten inspection note as a PNG image.
    Uses PIL to draw text that mimics handwriting appearance.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import random

        # Create slightly off-white background (simulates scanned paper)
        img = Image.new("RGB", (800, 600), color=(248, 245, 235))
        draw = ImageDraw.Draw(img)

        # Simulate handwritten note with slightly irregular positioning
        lines = [
            "Property Inspection Notes",
            "Date: Feb 15, 2025",
            "",
            "Unit: 742 Evergreen Terrace Apt 3B",
            "Inspector: Harvey Specter",
            "",
            "Findings:",
            "- Kitchen cabinets: 3 doors damaged, hinges broken",
            "- Bathroom: toilet running, tiles cracked near tub",
            "- Living room: large stain on carpet (approx 4x4 ft)",
            "- Bedroom window: latch broken, does not lock",
            "",
            "Total damage estimate: ~$2,100",
            "Beyond normal wear & tear: YES",
            "",
            "Tenant notified: NO (not present at inspection)",
            "Photos taken: YES (see attached)",
            "",
            "Signed: H. Specter  2/15/25",
        ]

        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        y = 40
        for line in lines:
            # Slight random x offset to simulate handwriting
            x_offset = random.randint(-2, 3) if line else 0
            color = (20 + random.randint(0, 15), 20 + random.randint(0, 10), 80 + random.randint(0, 20))
            draw.text(
                (50 + x_offset, y),
                line,
                fill=color,
                font=font,
            )
            y += 28 if line else 10

        # Add slight noise/grain effect
        import random as rnd
        pixels = img.load()
        for _ in range(3000):
            x = rnd.randint(0, img.width - 1)
            y_p = rnd.randint(0, img.height - 1)
            noise = rnd.randint(-15, 15)
            r, g, b = pixels[x, y_p]
            pixels[x, y_p] = (
                max(0, min(255, r + noise)),
                max(0, min(255, g + noise)),
                max(0, min(255, b + noise)),
            )

        out_path = OUTPUT_DIR / "inspection_note.png"
        img.save(str(out_path))
        print(f"Created: {out_path}")
        return out_path

    except ImportError as e:
        print(f"PIL not available: {e} — skipping image creation")
        return None


if __name__ == "__main__":
    print("Generating sample legal documents...")
    create_lease_agreement()
    create_eviction_notice()
    create_property_inspection_note()
    print("\nDone! Sample documents are in sample_docs/")
    print("Run the demo: python demo.py")
