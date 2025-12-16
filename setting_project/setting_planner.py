from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from collections import defaultdict
import os
import io
from datetime import datetime

app = Flask(__name__)
CORS(app)  # מאפשר קריאות מה-React frontend

# תיקיות לשמירת קבצים
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def read_and_split_excel(file_path, sheet_name="רשימת מוזמנים"):
    """
    קריאת קובץ אקסל/CSV וחלוקה לשני DataFrames (צד כלה וצד חתן)
    כאשר הם מופיעים זה לצד זה באותה שורה.
    """
    # 1. טעינת הקובץ בהתאם לסוגו
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path, header=None)
    else:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    
    bride_col = None
    groom_col = None
    title_row_idx = None
    
    # 2. סריקת הקובץ למציאת המיקום (שורה ועמודה) של הכותרות "הצד של..."
    for r_idx, row in df.iterrows():
        # המרת השורה לרשימה של טקסטים כדי שנוכל לחפש בה
        row_values = row.astype(str).tolist()
        
        for c_idx, val in enumerate(row_values):
            if "הצד של הכלה" in val:
                bride_col = c_idx
                title_row_idx = r_idx
            if "הצד של החתן" in val:
                groom_col = c_idx
                title_row_idx = r_idx 

        # אם מצאנו את שני הצדדים, עוצרים את החיפוש
        if bride_col is not None and groom_col is not None:
            break
            
    # בדיקה שמצאנו הכל
    if bride_col is None or groom_col is None:
        raise ValueError("לא נמצאו הכותרות 'הצד של הכלה' ו'הצד של החתן' בקובץ")
    
    # 3. חישוב מיקום שורת כותרות העמודות (שם, טלפון, קרבה...)
    # ההנחה היא שהן נמצאות בדיוק שורה אחת מתחת לכותרת הראשית
    headers_row_idx = title_row_idx + 1
    
    # 4. חיתוך הטבלה (Slicing) ויצירת טבלאות נפרדות
    
    # --- יצירת טבלה לצד הכלה ---
    # לוקחים נתונים מהשורה שאחרי הכותרות, ומהעמודה של הכלה עד העמודה של החתן
    bride_df = df.iloc[headers_row_idx+1:, bride_col:groom_col].copy()
    # לוקחים את שמות העמודות משורת הכותרות
    bride_df.columns = df.iloc[headers_row_idx, bride_col:groom_col].tolist()
    
    # --- יצירת טבלה לצד החתן ---
    # לוקחים נתונים מהעמודה של החתן ועד הסוף
    groom_df = df.iloc[headers_row_idx+1:, groom_col:].copy()
    groom_df.columns = df.iloc[headers_row_idx, groom_col:].tolist()
    
    # 5. תיקון קריטי: ניקוי רווחים משמות העמודות
    # זה מה שפותר את השגיאה עם "שם מלא " (הופך אותו ל-"שם מלא")
    bride_df.columns = bride_df.columns.astype(str).str.strip()
    groom_df.columns = groom_df.columns.astype(str).str.strip()
    
    # 6. ניקוי שורות ריקות וסינון
    # מחיקת שורות שכולן ריקות (למשל רווחים בין פסקאות באקסל)
    bride_df = bride_df.dropna(how='all')
    groom_df = groom_df.dropna(how='all')
    
    # סינון שורות שאין בהן שם מוזמן (כדי להעיף שורות סיכום או לכלוך)
    if 'שם מלא' in bride_df.columns:
        bride_df = bride_df[bride_df['שם מלא'].notna()]
    
    if 'שם מלא' in groom_df.columns:
        groom_df = groom_df[groom_df['שם מלא'].notna()]

    return bride_df, groom_df


def apply_filters(df, filters):
    """
    החלת פילטרים על DataFrame בשמות עברית
    """
    filtered_df = df.copy()
    
    for column, values in filters.items():
        if column in filtered_df.columns and values:
            filtered_df = filtered_df[filtered_df[column].isin(values)]
    
    return filtered_df.reset_index(drop=True)


def group_into_tables(df, table_size):
    """
    קיבוץ אורחים לשולחנות לפי קרבה וכמות מוזמנים
    """
    grouped = df.groupby('קרבה', dropna=False)
    
    tables = []
    table_number = 1
    
    for kraba, group in grouped:
        current_table = {
            'guests': [],
            'total_count': 0,
            'kraba': kraba
        }
        
        for _, row in group.iterrows():
            guest_name = row['שם מלא']
            guest_count = int(row['מוזמנים']) if pd.notna(row['מוזמנים']) else 1
            
            # אם מוסיפים את האורח הזה חורגים מגודל השולחן, פותחים שולחן חדש
            if current_table['total_count'] + guest_count > table_size and current_table['guests']:
                tables.append({
                    'מספר שולחן': table_number,
                    'קרבה': current_table['kraba'],
                    'שמות מוזמנים': ', '.join(current_table['guests']),
                    'כמות מוזמנים בשולחן': current_table['total_count']
                })
                table_number += 1
                current_table = {
                    'guests': [],
                    'total_count': 0,
                    'kraba': kraba
                }
            
            current_table['guests'].append(guest_name)
            current_table['total_count'] += guest_count
        
        # הוספת השולחן האחרון של קבוצת הקרבה
        if current_table['guests']:
            tables.append({
                'מספר שולחן': table_number,
                'קרבה': current_table['kraba'],
                'שמות מוזמנים': ', '.join(current_table['guests']),
                'כמות מוזמנים בשולחן': current_table['total_count']
            })
            table_number += 1
    
    return tables


@app.route('/api/process', methods=['POST'])
def process_seating():
    """
    API endpoint לעיבוד הקובץ וסידור השולחנות
    """
    try:
        # קבלת הקובץ והפרמטרים
        if 'file' not in request.files:
            return jsonify({'error': 'לא הועלה קובץ'}), 400
        
        file = request.files['file']
        table_type = request.form.get('table_type', 'regular')
        seats_per_table = int(request.form.get('seats_per_table', 10))
        
        # פילטרים אופציונליים
        kraba_filter = request.form.get('kraba_filter', '')
        name_filter = request.form.get('name_filter', '')
        guests_filter = request.form.get('guests_filter', '')
        
        # שמירת הקובץ
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"input_{timestamp}.xlsx"
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        # קריאת הנתונים
        bride_df, groom_df = read_and_split_excel(file_path)
        
        # בניית פילטרים
        filters = {}
        if kraba_filter:
            filters['קרבה'] = [k.strip() for k in kraba_filter.split(',')]
        if name_filter:
            filters['שם מלא'] = [n.strip() for n in name_filter.split(',')]
        if guests_filter:
            filters['מוזמנים'] = [int(g.strip()) for g in guests_filter.split(',') if g.strip().isdigit()]
        
        # החלת פילטרים
        if filters:
            bride_df = apply_filters(bride_df, filters)
            groom_df = apply_filters(groom_df, filters)
        
        # קיבוץ לשולחנות
        bride_tables = group_into_tables(bride_df, seats_per_table)
        groom_tables = group_into_tables(groom_df, seats_per_table)
        
        # יצירת קובץ פלט
        output_filename = f"seating_arrangement_{timestamp}.xlsx"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            bride_tables_df = pd.DataFrame(bride_tables)
            groom_tables_df = pd.DataFrame(groom_tables)
            
            bride_tables_df.to_excel(writer, sheet_name='הצד של הכלה', index=False)
            groom_tables_df.to_excel(writer, sheet_name='הצד של החתן', index=False)
        
        # החזרת תוצאות
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


@app.route('/api/analyze', methods=['POST'])
def analyze_file():
    """
    ניתוח ראשוני של הקובץ להצגת אפשרויות פילטור
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
        
        # איסוף ערכים ייחודיים לפילטרים
        analysis = {
            'bride': {
                'count': len(bride_df),
                'kraba_values': bride_df['קרבה'].unique().tolist() if 'קרבה' in bride_df.columns else [],
                'total_guests': int(bride_df['מוזמנים'].sum()) if 'מוזמנים' in bride_df.columns else 0
            },
            'groom': {
                'count': len(groom_df),
                'kraba_values': groom_df['קרבה'].unique().tolist() if 'קרבה' in groom_df.columns else [],
                'total_guests': int(groom_df['מוזמנים'].sum()) if 'מוזמנים' in groom_df.columns else 0
            }
        }
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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