import sqlite3

conn = sqlite3.connect('/home/SCSEkspedisiku/Ekspedisiku/database.db')
cursor = conn.cursor()

# 1. Buat tabel settings jika belum ada
cursor.execute('''
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY DEFAULT 1,
    print_method TEXT DEFAULT 'browser',
    resi_prefix TEXT DEFAULT '',
    resi_date_format TEXT DEFAULT '%Y%m%d',
    resi_counter_length INTEGER DEFAULT 4,
    resi_last_number INTEGER DEFAULT 0,
    company_address TEXT DEFAULT '',
    company_phone TEXT DEFAULT ''
)
''')

# 2. Tambahkan kolom resi_last_month jika belum ada
try:
    cursor.execute("ALTER TABLE settings ADD COLUMN resi_last_month INTEGER DEFAULT 0")
    print("✅ Kolom resi_last_month berhasil ditambahkan.")
except sqlite3.OperationalError:
    print("ℹ️ Kolom resi_last_month sudah ada.")

# 3. Pastikan ada baris settings dengan id=1
cursor.execute("SELECT COUNT(*) FROM settings WHERE id=1")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO settings (id) VALUES (1)")
    print("✅ Baris settings dibuat.")
else:
    print("ℹ️ Baris settings sudah ada.")

conn.commit()
conn.close()
print("🎉 Database siap digunakan!")