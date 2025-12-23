# ===============================
# Imports
# ===============================
# Flask – backend web framework
# CORS – allow frontend requests from other domains
# pandas – Excel/CSV processing
# defaultdict – grouping helper
# os / io / json – filesystem & data handling
# datetime – timestamping uploaded files

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from collections import defaultdict
import os
import io
import json
from datetime import datetime


# ===============================
# Global Configuration
# ===============================

# Flag to control whether family members can be split
NO_FAMILY_SPLIT = True

app = Flask(__name__)
CORS(app)

# Folders for uploaded input files and generated output files
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'

# Ensure folders exist on server startup
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# =====================================================
# Excel Parsing
# =====================================================
def read_and_split_excel(file_path, sheet_name="רשימת מוזמנים"):
    """
    Reads an Excel or CSV guest list and splits it into:
    - Bride side DataFrame
    - Groom side DataFrame

    The function:
    1. Locates the columns titled:
       'הצד של הכלה' and 'הצד של החתן'
    2. Extracts the relevant columns for each side
    3. Cleans empty rows and missing names
    """

    # Load file depending on extension
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path, header=None)
    else:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)

    bride_col = None
    groom_col = None
    title_row_idx = None

    # Search for the columns that mark bride/groom sections
    for r_idx, row in df.iterrows():
        row_values = row.astype(str).tolist()

        for c_idx, val in enumerate(row_values):
            if "הצד של הכלה" in val:
                bride_col = c_idx
                title_row_idx = r_idx
            if "הצד של החתן" in val:
                groom_col = c_idx
                title_row_idx = r_idx

        if bride_col is not None and groom_col is not None:
            break

    if bride_col is None or groom_col is None:
        raise ValueError("לא נמצאו הכותרות 'הצד של הכלה' ו'הצד של החתן' בקובץ")

    # Row containing column names (e.g. שם מלא, קרבה, מוזמנים)
    headers_row_idx = title_row_idx + 1

    # Extract bride side
    bride_df = df.iloc[headers_row_idx + 1:, bride_col:groom_col].copy()
    bride_df.columns = df.iloc[headers_row_idx, bride_col:groom_col].tolist()

    # Extract groom side
    groom_df = df.iloc[headers_row_idx + 1:, groom_col:].copy()
    groom_df.columns = df.iloc[headers_row_idx, groom_col:].tolist()

    # Normalize column names
    bride_df.columns = bride_df.columns.astype(str).str.strip()
    groom_df.columns = groom_df.columns.astype(str).str.strip()

    # Remove fully empty rows
    bride_df = bride_df.dropna(how='all')
    groom_df = groom_df.dropna(how='all')

    # Ensure guests have names
    if 'שם מלא' in bride_df.columns:
        bride_df = bride_df[bride_df['שם מלא'].notna()]

    if 'שם מלא' in groom_df.columns:
        groom_df = groom_df[groom_df['שם מלא'].notna()]

    return bride_df, groom_df


# =====================================================
# Filtering Helpers
# =====================================================
def apply_filters(df, filters):
    """
    Applies column-based filters to a DataFrame.
    Example:
    filters = {'קרבה': ['חברים', 'משפחה']}
    """
    filtered_df = df.copy()

    for column, values in filters.items():
        if column in filtered_df.columns and values:
            filtered_df = filtered_df[filtered_df[column].isin(values)]

    return filtered_df.reset_index(drop=True)


def find_oversized_groups(df, table_size):
    """
    Detects relation groups that exceed the table size
    (excluding parents).
    Used to ask the user how to handle them.
    """
    overSized = []

    if df.empty or 'קרבה' not in df.columns:
        return overSized

    grouped = df.groupby('קרבה', dropna=False)

    for relation, group in grouped:
        # Parents are handled separately
        if relation in ['משפחה אמא', 'משפחה אבא']:
            continue

        total_guests = int(group['מוזמנים'].fillna(1).astype(int).sum())

        if total_guests > table_size:
            overSized.append({
                'relation': relation,
                'total_guests': total_guests,
                'guests': group['שם מלא'].tolist()
            })

    return overSized


# =====================================================
# Seating Logic
# =====================================================
def group_into_tables(
    df,
    table_size,
    aba_preference='separate',
    ima_preference='separate',
    oversized_decisions=None
):
    """
    Core seating algorithm.

    Rules:
    - Parent families (אבא / אמא) have special handling
    - ≤12 guests → always one table
    - 13–22 guests → user decides (Knight vs Separate)
    - Oversized non-parent groups may be forced into Knight tables
    """

    if df.empty:
        return []

    tables = []
    current_table_num = 1

    # Map relation → user decision
    oversized_config = {}
    if oversized_decisions:
        for decision in oversized_decisions:
            if 'relation' in decision and 'action' in decision:
                oversized_config[decision['relation']] = decision['action']

    def add_to_tables(guest_list, relation_name, is_knight=False):
        """
        Internal helper to append a table to the results list.
        """
        nonlocal current_table_num

        names = ', '.join([str(g['name']) for g in guest_list])
        total = sum([g['count'] for g in guest_list])

        table_label = f"אביר {current_table_num}" if is_knight else current_table_num

        tables.append({
            'מספר שולחן': table_label,
            'סוג שולחן': 'אביר' if is_knight else 'רגיל',
            'קרבה': relation_name,
            'שמות מוזמנים': names,
            'כמות מוזמנים בשולחן': total
        })

        current_table_num += 1

    # -------------------------------
    # PART 1: Parents (Aba & Ima)
    # -------------------------------
    for parent_type, pref in [('משפחה אבא', aba_preference), ('משפחה אמא', ima_preference)]:
        parent_df = df[df['קרבה'] == parent_type]
        if parent_df.empty:
            continue

        total_count = int(parent_df['מוזמנים'].fillna(1).astype(int).sum())
        all_guests = [{'name': r['שם מלא'], 'count': int(r['מוזמנים'] or 1)}
                      for _, r in parent_df.iterrows()]

        # Force single table if small or user chose Knight
        if total_count <= 12 or (total_count <= 22 and pref == 'knight'):
            add_to_tables(all_guests, parent_type, is_knight=(total_count > 12))
        else:
            # Split into regular tables
            current_batch, current_sum = [], 0
            for guest in all_guests:
                if current_sum + guest['count'] > table_size and current_batch:
                    add_to_tables(current_batch, parent_type)
                    current_batch, current_sum = [], 0
                current_batch.append(guest)
                current_sum += guest['count']

            if current_batch:
                add_to_tables(current_batch, parent_type)

    # -------------------------------
    # PART 2: Everyone else
    # -------------------------------
    others_df = df[~df['קרבה'].isin(['משפחה אבא', 'משפחה אמא'])]

    for relation, group in others_df.groupby('קרבה', dropna=False):
        all_guests = [{'name': r['שם מלא'], 'count': int(r['מוזמנים'] or 1)}
                      for _, r in group.iterrows()]

        if oversized_config.get(relation) == 'bigger_table':
            add_to_tables(all_guests, relation, is_knight=True)
        else:
            current_batch, current_sum = [], 0
            for guest in all_guests:
                if current_sum + guest['count'] > table_size and current_batch:
                    add_to_tables(current_batch, relation)
                    current_batch, current_sum = [], 0
                current_batch.append(guest)
                current_sum += guest['count']

            if current_batch:
                add_to_tables(current_batch, relation)

    return tables


def check_parent_groups(df):
    """
    בדיקת גודל קבוצות משפחה אבא ואמא
    """
    parent_groups = ['משפחה אבא', 'משפחה אמא']
    parent_df = df[df['קרבה'].isin(parent_groups)]
    
    if parent_df.empty:
        return None
    
    aba_df = parent_df[parent_df['קרבה'] == 'משפחה אבא']
    ima_df = parent_df[parent_df['קרבה'] == 'משפחה אמא']
    
    aba_count = int(aba_df['מוזמנים'].fillna(1).astype(int).sum()) if not aba_df.empty else 0
    ima_count = int(ima_df['מוזמנים'].fillna(1).astype(int).sum()) if not ima_df.empty else 0
    
    return {
        'aba_count': aba_count,
        'ima_count': ima_count,
        'aba_needs_decision': 12 < aba_count <= 22,
        'ima_needs_decision': 12 < ima_count <= 22
    }


@app.route('/api/analyze', methods=['POST'])
def analyze_file():
    """
    ניתוח ראשוני של הקובץ
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'לא הועלה קובץ'}), 400
        
        file = request.files['file']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"analyze_{timestamp}.xlsx"
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        bride_df, groom_df = read_and_split_excel(file_path)
        
        analysis = {
            'bride': {
                'count': len(bride_df),
                'kraba_values': bride_df['קרבה'].unique().tolist() if 'קרבה' in bride_df.columns else [],
                'total_guests': int(bride_df['מוזמנים'].sum()) if 'מוזמנים' in bride_df.columns else 0,
                'parent_info': check_parent_groups(bride_df)
            },
            'groom': {
                'count': len(groom_df),
                'kraba_values': groom_df['קרבה'].unique().tolist() if 'קרבה' in groom_df.columns else [],
                'total_guests': int(groom_df['מוזמנים'].sum()) if 'מוזמנים' in groom_df.columns else 0,
                'parent_info': check_parent_groups(groom_df)
            }
        }
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process_seating():
    """
    API endpoint לעיבוד הקובץ וסידור השולחנות
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'לא הועלה קובץ'}), 400

        table_size = int(request.form.get('table_size', 10)) 
        file = request.files['file']
        table_type = request.form.get('table_type', 'regular')
        seats_per_table = int(request.form.get('seats_per_table', 10))
        knight_table_count = int(request.form.get('knight_table_count', 0))
        knight_group = request.form.get('knight_group', '')
        aba_preference = request.form.get('aba_preference', 'separate')
        ima_preference = request.form.get('ima_preference', 'separate')
        oversized_decisions_json = request.form.get('oversized_decisions', '[]')
        oversized_decisions = json.loads(oversized_decisions_json)
    

        kraba_filter = request.form.get('kraba_filter', '')
        min_guests = request.form.get('min_guests', '')
        max_guests = request.form.get('max_guests', '')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"input_{timestamp}.xlsx"
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        bride_df, groom_df = read_and_split_excel(file_path)

        bride_oversized = [d for d in oversized_decisions if d.get('side') == 'bride']
        groom_oversized = [d for d in oversized_decisions if d.get('side') == 'groom']
    
        # NEW: Pass decisions to grouping function
        bride_tables = group_into_tables(bride_df, seats_per_table, aba_preference, ima_preference, bride_oversized)

        bride_oversized = find_oversized_groups(bride_df, table_size)
        groom_oversized = find_oversized_groups(groom_df, table_size)

        analysis = {
        'bride': {
            'oversized_groups': bride_oversized  # NEW!
        },
        'groom': {
            'oversized_groups': groom_oversized  # NEW!
        }
    }
    
        
        if kraba_filter:
            select_kraba = [k.strip() for k in kraba_filter.split('.')]
            bride_df = bride_df[bride_df['קרבה'].isin(select_kraba)]
            groom_df = groom_df[groom_df['קרבה'].isin(select_kraba)]
        
        if min_guests:
            min_val = int(min_guests)
            bride_df = bride_df[bride_df['מוזמנים'].fillna(1).astype(int) >= min_val]
            groom_df = groom_df[groom_df['מוזמנים'].fillna(1).astype(int) >= min_val]

        if max_guests:
            max_val = int(max_guests)
            bride_df = bride_df[bride_df['מוזמנים'].fillna(1).astype(int) <= max_val]
            groom_df = groom_df[groom_df['מוזמנים'].fillna(1).astype(int) <= max_val]

        bride_knight, bride_df = extract_knight_tables(
            bride_df, knight_group, knight_table_count
        )

        groom_knight, groom_df = extract_knight_tables(
            groom_df, knight_group, knight_table_count
        )
        
        bride_tables = group_into_tables(bride_df, seats_per_table, aba_preference, ima_preference)
        groom_tables = group_into_tables(groom_df, seats_per_table, aba_preference, ima_preference)

        bride_tables = bride_knight + bride_tables
        groom_tables = groom_knight + groom_tables
        
        output_filename = f"seating_arrangement_{timestamp}.xlsx"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            bride_tables_df = pd.DataFrame(bride_tables)
            groom_tables_df = pd.DataFrame(groom_tables)
            
            bride_tables_df.to_excel(writer, sheet_name='הצד של הכלה', index=False)
            groom_tables_df.to_excel(writer, sheet_name='הצד של החתן', index=False)
        
        return jsonify({
            'success': True,
            'message': 'הקובץ עובד בהצלחה!',
            'stats': {
                'bride_entries': len(bride_df),
                'groom_entries': len(groom_df),
                'bride_tables': len(bride_tables),
                'groom_tables': len(groom_tables),
                'table_type': 'שולחן אביר' if table_type == 'knight' else 'שולחן רגיל',
                'seats_per_table': seats_per_table
            },
            'download_url': f'/api/download/{output_filename}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

def extract_knight_tables(df, knight_group, knight_table_count):
    KNIGHT_TABLE_SIZE = 22

    if knight_table_count <= 0 or not knight_group:
        return [], df

    knight_df = df[df['קרבה'] == knight_group].copy()

    tables = []
    used_seats = 0
    table_number = 1
    current_table = []

    for _, row in knight_df.iterrows():
        guest_count = int(row['מוזמנים']) if pd.notna(row['מוזמנים']) else 1

        if used_seats + guest_count > knight_table_count * KNIGHT_TABLE_SIZE:
            break

        if len(current_table) + guest_count >= KNIGHT_TABLE_SIZE:
            tables.append({
                'מספר שולחן': f"אביר {table_number}",
                'קרבה': knight_group,
                'שמות מוזמנים': ', '.join(current_table),
                'כמות מוזמנים בשולחן': len(current_table)
            })
            table_number += 1
            current_table = []

        current_table.append(row['שם מלא'])
        used_seats += guest_count

    if current_table:
        tables.append({
            'מספר שולחן': f"אביר {table_number}",
            'קרבה': knight_group,
            'שמות מוזמנים': ', '.join(current_table),
            'כמות מוזמנים בשולחן': len(current_table)
        })

    remaining_df = df.drop(knight_df.index)

    return tables, remaining_df


@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """
    הורדת קובץ הפלט
    """
    try:
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 404


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    בדיקת תקינות השרת
    """
    return jsonify({
        'status': 'healthy',
        'message': 'Wedding Seating API is running'
    })


if __name__ == '__main__':
    print("🚀 Starting Wedding Seating Arrangement API Server...")
    print("📍 Server running on http://localhost:5000")
    print("💡 Use /api/process to process files")
    print("💡 Use /api/analyze to analyze files")
    print("💡 Use /api/download/<filename> to download results")
    app.run(debug=True, host='0.0.0.0', port=5000)