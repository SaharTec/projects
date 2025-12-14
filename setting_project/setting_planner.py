import streamlit as st
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import io

@dataclass
class Guest:
    """Represents a single guest"""
    name: str
    side: str
    sub_side: str
    role: str
    
    def is_family(self) -> bool:
        """Check if guest is family (not Other role)"""
        return self.role in ['Grandpa', 'Grandma', 'Uncle', 'Aunt']

@dataclass
class Table:
    """Represents a seating table"""
    number: int
    side: str
    table_type: str  # 'Family' or 'Regular'
    guests: List[Guest]
    
    def add_guest(self, guest: Guest):
        """Add a guest to the table"""
        self.guests.append(guest)
    
    def guest_count(self) -> int:
        """Get number of guests at table"""
        return len(self.guests)

class SeatingValidator:
    """Validates seating arrangements against rules"""
    
    @staticmethod
    def get_minimum_seats(table_size: int) -> int:
        """Get minimum allowed guests for a table size"""
        minimums = {10: 8, 11: 9, 12: 10}
        return minimums.get(table_size, 8)
    
    @staticmethod
    def validate_tables(tables: List[Table], table_size: int) -> Tuple[bool, List[str]]:
        """Validate all tables meet minimum requirements"""
        errors = []
        min_seats = SeatingValidator.get_minimum_seats(table_size)
        
        for table in tables:
            if table.guest_count() < min_seats:
                errors.append(
                    f"Table {table.number} ({table.side} - {table.table_type}) "
                    f"has only {table.guest_count()} guests, minimum is {min_seats}"
                )
        
        return len(errors) == 0, errors

class ExcelParser:
    """Handles Excel file parsing"""
    
    # Support both English and Hebrew sheet names
    SHEET_MAPPINGS = {
        'Bride Side': ['Bride Side', 'צד כלה'],
        'Groom Side': ['Groom Side', 'צד חתן'],
        'Bride Friends': ['Bride Friends', 'חברים כלה'],
        'Groom Friends': ['Groom Friends', 'חברים חתן']
    }
    
    # Support both English and Hebrew column names
    COLUMN_MAPPINGS = {
        'Name': ['Name', 'שם ושם משפחה'],
        'Side': ['Side', 'צד'],
        'SubSide': ['SubSide', 'מוזמנים'],
        'Role': ['Role', 'תפקיד']
    }
    
    @staticmethod
    def _find_column(df: pd.DataFrame, canonical_name: str) -> Optional[str]:
        """Find which column name exists in the dataframe"""
        possible_names = ExcelParser.COLUMN_MAPPINGS.get(canonical_name, [canonical_name])
        for name in possible_names:
            if name in df.columns:
                return name
        return None
    
    @staticmethod
    def parse_excel(file) -> Tuple[List[Guest], List[str]]:
        """Parse Excel file and return list of guests"""
        guests = []
        errors = []
        
        try:
            excel_file = pd.ExcelFile(file)
            
            # Map sheet names (support both English and Hebrew)
            for canonical_name, possible_names in ExcelParser.SHEET_MAPPINGS.items():
                # Find which name exists in the file
                found_sheet = None
                for name in possible_names:
                    if name in excel_file.sheet_names:
                        found_sheet = name
                        break
                
                if found_sheet is None:
                    errors.append(f"Missing required sheet: {' or '.join(possible_names)}")
                    continue
                
                df = pd.read_excel(excel_file, sheet_name=found_sheet)
                
                # Map column names
                column_map = {}
                missing_cols = []
                
                for canonical_col in ['Name', 'Side', 'SubSide', 'Role']:
                    found_col = ExcelParser._find_column(df, canonical_col)
                    if found_col:
                        column_map[canonical_col] = found_col
                    else:
                        missing_cols.append(f"{canonical_col} ({' or '.join(ExcelParser.COLUMN_MAPPINGS[canonical_col])})")
                
                if missing_cols:
                    errors.append(f"Sheet '{found_sheet}' missing columns: {', '.join(missing_cols)}")
                    continue
                
                # Parse guests from this sheet
                for _, row in df.iterrows():
                    # Skip rows with missing name
                    name_col = column_map['Name']
                    if pd.isna(row[name_col]) or str(row[name_col]).strip() == '':
                        continue
                    
                    side_col = column_map['Side']
                    subside_col = column_map['SubSide']
                    role_col = column_map['Role']
                    
                    guest = Guest(
                        name=str(row[name_col]).strip(),
                        side=str(row[side_col]).strip() if not pd.isna(row[side_col]) else '',
                        sub_side=str(row[subside_col]).strip() if not pd.isna(row[subside_col]) else '',
                        role=str(row[role_col]).strip() if not pd.isna(row[role_col]) else 'Other'
                    )
                    guests.append(guest)
            
        except Exception as e:
            errors.append(f"Error reading Excel file: {str(e)}")
        
        return guests, errors

class SeatingArranger:
    """Main seating arrangement logic"""
    
    def __init__(self, table_size: int, special_table: bool):
        self.table_size = table_size
        self.special_table = special_table
        self.min_seats = SeatingValidator.get_minimum_seats(table_size)
        self.table_counter = 1
    
    def arrange_seating(self, guests: List[Guest]) -> Tuple[Optional[List[Table]], List[str]]:
        """Generate seating arrangement"""
        tables = []
        errors = []
        
        # Separate guests by side
        bride_guests = [g for g in guests if g.side == 'Bride']
        groom_guests = [g for g in guests if g.side == 'Groom']
        
        # Process Bride side
        bride_tables, bride_errors = self._process_side(bride_guests, 'Bride')
        if bride_errors:
            errors.extend(bride_errors)
        else:
            tables.extend(bride_tables)
        
        # Process Groom side
        groom_tables, groom_errors = self._process_side(groom_guests, 'Groom')
        if groom_errors:
            errors.extend(groom_errors)
        else:
            tables.extend(groom_tables)
        
        # If there were errors, return None for tables
        if errors:
            return None, errors
        
        # Final validation
        is_valid, validation_errors = SeatingValidator.validate_tables(tables, self.table_size)
        if not is_valid:
            return None, validation_errors
        
        return tables, []
    
    def _process_side(self, guests: List[Guest], side: str) -> Tuple[List[Table], List[str]]:
        """Process one side (Bride or Groom)"""
        tables = []
        errors = []
        
        # Separate family and friends
        family_guests = [g for g in guests if g.is_family()]
        friends = [g for g in guests if g.role == 'Other' and (side + ' Friends' in ['Bride Friends', 'Groom Friends'])]
        other_guests = [g for g in guests if not g.is_family() and g not in friends]
        
        # Create family table
        if family_guests:
            family_table = Table(
                number=self.table_counter,
                side=side,
                table_type='Family',
                guests=[]
            )
            self.table_counter += 1
            
            for guest in family_guests:
                family_table.add_guest(guest)
            
            # Check if family table meets minimum
            if family_table.guest_count() < self.min_seats:
                errors.append(
                    f"{side} family table has only {family_table.guest_count()} guests, "
                    f"minimum is {self.min_seats}. Suggestions:\n"
                    f"  • Use a smaller table size\n"
                    f"  • Allow mixing sides (contact support)\n"
                    f"  • Add more family members"
                )
                return [], errors
            
            tables.append(family_table)
        
        # Separate non-family guests by SubSide (Mother/Father)
        mother_guests = [g for g in other_guests if g.sub_side == 'Mother']
        father_guests = [g for g in other_guests if g.sub_side == 'Father']
        no_subside_guests = [g for g in other_guests if g.sub_side not in ['Mother', 'Father']]
        
        # Create tables for Mother side
        mother_tables, mother_errors = self._create_tables_for_group(
            mother_guests, side, 'Regular (Mother Side)'
        )
        if mother_errors:
            errors.extend(mother_errors)
            return [], errors
        tables.extend(mother_tables)
        
        # Create tables for Father side
        father_tables, father_errors = self._create_tables_for_group(
            father_guests, side, 'Regular (Father Side)'
        )
        if father_errors:
            errors.extend(father_errors)
            return [], errors
        tables.extend(father_tables)
        
        # Create tables for guests without SubSide
        other_tables, other_errors = self._create_tables_for_group(
            no_subside_guests, side, 'Regular'
        )
        if other_errors:
            errors.extend(other_errors)
            return [], errors
        tables.extend(other_tables)
        
        # Create tables for friends
        friend_tables, friend_errors = self._create_tables_for_group(
            friends, side, 'Regular (Friends)'
        )
        if friend_errors:
            errors.extend(friend_errors)
            return [], errors
        tables.extend(friend_tables)
        
        return tables, []
    
    def _create_tables_for_group(
        self, 
        guests: List[Guest], 
        side: str, 
        table_type: str
    ) -> Tuple[List[Table], List[str]]:
        """Create tables for a specific group of guests"""
        if not guests:
            return [], []
        
        tables = []
        errors = []
        remaining_guests = guests.copy()
        
        # Create special table if requested and we have enough guests
        if self.special_table and len(remaining_guests) >= 20:
            special_table = Table(
                number=self.table_counter,
                side=side,
                table_type=table_type,
                guests=remaining_guests[:20]
            )
            self.table_counter += 1
            tables.append(special_table)
            remaining_guests = remaining_guests[20:]
        
        # Create regular tables
        while remaining_guests:
            table = Table(
                number=self.table_counter,
                side=side,
                table_type=table_type,
                guests=[]
            )
            self.table_counter += 1
            
            # Fill table up to table_size
            guests_to_add = min(self.table_size, len(remaining_guests))
            for _ in range(guests_to_add):
                table.add_guest(remaining_guests.pop(0))
            
            tables.append(table)
        
        # Check if last table meets minimum
        if tables and tables[-1].guest_count() < self.min_seats:
            # Try to redistribute guests from previous table
            if len(tables) > 1:
                last_table = tables[-1]
                prev_table = tables[-2]
                
                # Calculate if we can redistribute
                total = last_table.guest_count() + prev_table.guest_count()
                if total >= 2 * self.min_seats:
                    # Redistribute guests evenly
                    all_guests = prev_table.guests + last_table.guests
                    mid_point = len(all_guests) // 2
                    
                    prev_table.guests = all_guests[:mid_point]
                    last_table.guests = all_guests[mid_point:]
                else:
                    errors.append(
                        f"Cannot create valid seating for {side} {table_type}. "
                        f"Last table would have {last_table.guest_count()} guests, "
                        f"minimum is {self.min_seats}. Suggestions:\n"
                        f"  • Use a smaller table size\n"
                        f"  • Allow mixing sides or SubSides"
                    )
                    return [], errors
            else:
                errors.append(
                    f"Cannot create valid seating for {side} {table_type}. "
                    f"Only {tables[-1].guest_count()} guests available, "
                    f"minimum is {self.min_seats}. Suggestions:\n"
                    f"  • Use a smaller table size\n"
                    f"  • Combine with another group"
                )
                return [], errors
        
        return tables, []

def main():
    st.set_page_config(page_title="Event Seating Arrangement", page_icon="💺", layout="wide")
    
    st.title("💺 Event Seating Arrangement System")
    st.markdown("---")
    
    # File upload
    st.subheader("📤 Step 1: Upload Excel File")
    uploaded_file = st.file_uploader(
        "Upload your guest list Excel file",
        type=['xlsx', 'xls'],
        help="Sheets: צד כלה, צד חתן, חברים כלה, חברים חתן | Columns: שם ושם משפחה, צד, מוזמנים, תפקיד"
    )
    
    st.markdown("---")
    
    # Configuration options
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("⚙️ Step 2: Configure Tables")
        table_size = st.selectbox(
            "Select table size:",
            options=[10, 11, 12],
            help="Number of seats per table"
        )
        
        min_seats = SeatingValidator.get_minimum_seats(table_size)
        st.info(f"ℹ️ Minimum guests per table: {min_seats}")
    
    with col2:
        st.subheader("🌟 Step 3: Special Table")
        special_table = st.radio(
            "Do you want a special table of 20 people?",
            options=["No", "Yes"],
            horizontal=True
        ) == "Yes"
    
    st.markdown("---")
    
    # Generate button
    if st.button("🎯 Generate Seating Arrangement", type="primary", use_container_width=True):
        if uploaded_file is None:
            st.error("❌ Please upload an Excel file first!")
            return
        
        with st.spinner("Processing guest list and generating seating..."):
            # Parse Excel
            guests, parse_errors = ExcelParser.parse_excel(uploaded_file)
            
            if parse_errors:
                st.error("❌ Error parsing Excel file:")
                for error in parse_errors:
                    st.error(f"  • {error}")
                return
            
            if not guests:
                st.error("❌ No guests found in Excel file!")
                return
            
            st.success(f"✅ Successfully loaded {len(guests)} guests")
            
            # Generate seating
            arranger = SeatingArranger(table_size, special_table)
            tables, arrangement_errors = arranger.arrange_seating(guests)
            
            if arrangement_errors:
                st.error("❌ Cannot generate seating arrangement:")
                for error in arrangement_errors:
                    st.error(error)
                
                st.info("💡 **Suggestions:**")
                st.markdown("""
                - Try a **smaller table size** (10 instead of 12)
                - Contact support to enable **side mixing** for special cases
                - Review your guest list for accuracy
                """)
                return
            
            # Display results
            st.success("✅ Seating arrangement generated successfully!")
            st.markdown("---")
            
            # Display tables
            st.subheader("📋 Seating Arrangement")
            
            for table in tables:
                with st.expander(
                    f"**Table {table.number}** - {table.side} Side - {table.table_type} "
                    f"({table.guest_count()} guests)",
                    expanded=True
                ):
                    # Create guest list
                    guest_names = [g.name for g in table.guests]
                    
                    # Display in columns
                    cols = st.columns(3)
                    for idx, name in enumerate(guest_names):
                        with cols[idx % 3]:
                            st.write(f"• {name}")
            
            # Summary statistics
            st.markdown("---")
            st.subheader("📊 Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Tables", len(tables))
            
            with col2:
                total_guests = sum(t.guest_count() for t in tables)
                st.metric("Total Guests", total_guests)
            
            with col3:
                bride_tables = len([t for t in tables if t.side == 'Bride'])
                st.metric("Bride Tables", bride_tables)
            
            with col4:
                groom_tables = len([t for t in tables if t.side == 'Groom'])
                st.metric("Groom Tables", groom_tables)

if __name__ == "__main__":
    main()