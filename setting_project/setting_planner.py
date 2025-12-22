# ===================== Imports =====================
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from collections import defaultdict
import os
import io
import json
from datetime import datetime


# ===================== Global Configuration =====================

# Flag (currently unused) – could be used to prevent splitting families
NO_FAMILY_SPLIT = True

# Initialize Flask app
app = Flask(__name__)

# Enable CORS so frontend (different domain/port) can access the API
CORS(app)

# Folder paths for uploads and outputs
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'

# Ensure folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ===================== File Reading & Splitting =====================
def read_and_split_excel(file_path, sheet_name="רשימת מוזמנים"):
    """
    Reads an Excel or CSV file and splits it into two DataFrames:
    - Bride side
    - Groom side
    """

    # Read file depending on extension
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path, header=None)
    else:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)

    bride_col = None      # Column index where bride side starts
    groom_col = None      # Column index where groom side starts
    title_row_idx = None  # Row index of side titles

    # Scan the file to locate side titles
    for r_idx, row in df.iterrows():
        row_values = row.astype(str).tolist()

        for c_idx, val in enumerate(row_values):
            if "הצד של הכלה" in val:
                bride_col = c_idx
                title_row_idx = r_idx
            if "הצד של החתן" in val:
                groom_col = c_idx
                title_row_idx = r_idx

        # Stop once both sides are found
        if bride_col is not None and groom_col is not None:
            break

    # Fail fast if structure is invalid
    if bride_col is None or groom_col is None:
        raise ValueError("לא נמצאו הכותרות 'הצד של הכלה' ו'הצד של החתן' בקובץ")

    # Header row is directly below the title row
    headers_row_idx = title_row_idx + 1

    # Slice bride side columns
    bride_df = df.iloc[headers_row_idx + 1:, bride_col:groom_col].copy()
    bride_df.columns = df.iloc[headers_row_idx, bride_col:groom_col].tolist()

    # Slice groom side columns
    groom_df = df.iloc[headers_row_idx + 1:, groom_col:].copy()
    groom_df.columns = df.iloc[headers_row_idx, groom_col:].tolist()

    # Clean column names
    bride_df.columns = bride_df.columns.astype(str).str.strip()
    groom_df.columns = groom_df.columns.astype(str).str.strip()

    # Drop fully empty rows
    bride_df = bride_df.dropna(how='all')
    groom_df = groom_df.dropna(how='all')

    # Remove rows without a full name
    if 'שם מלא' in bride_df.columns:
        bride_df = bride_df[bride_df['שם מלא'].notna()]

    if 'שם מלא' in groom_df.columns:
        groom_df = groom_df[groom_df['שם מלא'].notna()]

    return bride_df, groom_df


# ===================== Filtering =====================
def apply_filters(df, filters):
    """
    Applies column-based filters to a DataFrame.
    Example:
    filters = {"קרבה": ["משפחה", "חברים"]}
    """
    filtered_df = df.copy()

    for column, values in filters.items():
        if column in filtered_df.columns and values:
            filtered_df = filtered_df[filtered_df[column].isin(values)]

    return filtered_df.reset_index(drop=True)


# ===================== Oversized Group Detection =====================
def find_oversized_groups(df, table_size):
    """
    Finds relationship groups that exceed table size.
    Used to ask user how to handle them.
    """
    overSized = []

    # No data or no relationship column
    if df.empty or 'קרבה' not in df.columns:
        return overSized

    # Group by relationship (קרבה)
    grouped = df.groupby('קרבה', dropna=False)

    for relation, group in grouped:
        # Skip parent families (handled separately)
        if relation in ['משפחה אמא', 'משפחה אבא']:
            continue

        # Count total guests in group
        total_guests = int(group['מוזמנים'].fillna(1).astype(int).sum())

        # Flag oversized groups
        if total_guests > table_size:
            overSized.append({
                'relation': relation,
                'total_guests': total_guests,
                'guests': group['שם מלא'].tolist()
            })

    return overSized


# ===================== Seating Logic =====================
def group_into_tables(
    df,
    table_size,
    aba_preference='separate',
    ima_preference='separate',
    oversized_decisions=None
):
    """
    Converts a guest DataFrame into a list of seating tables.

    Special logic:
    - Parents (Aba / Ima) handled separately
    - Knight tables supported
    - Oversized group decisions override default behavior
    """

    if df.empty:
        return []

    tables = []
    table_number = 1

    # Map oversized decisions by relation
    oversized_config = {}
    if oversized_decisions:
        for decision in oversized_decisions:
            oversized_config[decision['relation']] = decision['action']

    # ---------- Helper for Parent Families ----------
    def process_special_group(group_name, preference, current_table_number):
        """
        Handles Aba / Ima family logic.
        """
        group_df = df[df['קרבה'] == group_name]
        if group_df.empty:
            return [], current_table_number

        group_count = int(group_df['מוזמנים'].fillna(1).astype(int).sum())
        all_names = group_df['שם מלא'].tolist()
        new_tables = []

        # Case 1: Small group → single regular table
        if group_count <= 12:
            new_tables.append({
                'מספר שולחן': current_table_number,
                'סוג שולחן': 'רגיל',
                'קרבה': group_name,
                'שמות מוזמנים': ', '.join(all_names),
                'כמות מוזמנים בשולחן': group_count
            })
            current_table_number += 1

        # Case 2: Medium group + knight preference
        elif 12 < group_count <= 22 and preference == 'knight':
            new_tables.append({
                'מספר שולחן': f'אביר {current_table_number}',
                'סוג שולחן': 'אביר',
                'קרבה': group_name,
                'שמות מוזמנים': ', '.join(all_names),
                'כמות מוזמנים בשולחן': group_count
            })
            current_table_number += 1

        # Case 3: Large group or forced separation
        else:
            current_guests = []
            current_count = 0

            for _, row in group_df.iterrows():
                name = row['שם מלא']
                guests = int(row['מוזמנים']) if pd.notna(row['מוזמנים']) else 1

                # Start new table if overflow
                if current_count + guests > table_size and current_guests:
                    new_tables.append({
                        'מספר שולחן': current_table_number,
                        'סוג שולחן': 'רגיל',
                        'קרבה': group_name,
                        'שמות מוזמנים': ', '.join(current_guests),
                        'כמות מוזמנים בשולחן': current_count
                    })
                    current_table_number += 1
                    current_guests = []
                    current_count = 0

                current_guests.append(name)
                current_count += guests

            # Add remaining guests
            if current_guests:
                new_tables.append({
                    'מספר שולחן': current_table_number,
                    'סוג שולחן': 'רגיל',
                    'קרבה': group_name,
                    'שמות מוזמנים': ', '.join(current_guests),
                    'כמות מוזמנים בשולחן': current_count
                })
                current_table_number += 1

        return new_tables, current_table_number

    # ---------- Parent Groups ----------
    aba_tables, table_number = process_special_group(
        'משפחה אבא', aba_preference, table_number
    )
    tables.extend(aba_tables)

    ima_tables, table_number = process_special_group(
        'משפחה אמא', ima_preference, table_number
    )
    tables.extend(ima_tables)

    # ---------- All Other Guests ----------
    other_df = df[~df['קרבה'].isin(['משפחה אבא', 'משפחה אמא'])].copy()
    grouped = other_df.groupby('קרבה', dropna=False)

    for relation, group in grouped:
        current_guests = []
        current_count = 0

        for _, row in group.iterrows():
            name = row['שם מלא']
            guests = int(row['מוזמנים']) if pd.notna(row['מוזמנים']) else 1

            if current_count + guests > table_size and current_guests:
                tables.append({
                    'מספר שולחן': table_number,
                    'סוג שולחן': 'רגיל',
                    'קרבה': relation,
                    'שמות מוזמנים': ', '.join(current_guests),
                    'כמות מוזמנים בשולחן': current_count
                })
                table_number += 1
                current_guests = []
                current_count = 0

            current_guests.append(name)
            current_count += guests

        if current_guests:
            tables.append({
                'מספר שולחן': table_number,
                'סוג שולחן': 'רגיל',
                'קרבה': relation,
                'שמות מוזמנים': ', '.join(current_guests),
                'כמות מוזמנים בשולחן': current_count
            })
            table_number += 1

    return tables