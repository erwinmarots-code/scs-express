import os
import barcode
from barcode.writer import ImageWriter
from datetime import datetime
from models import db, Settings, Pengiriman, Pelanggan, BiayaOperasional
import pandas as pd

def generate_resi_number():
    settings = Settings.get()
    prefix = settings.resi_prefix
    date_format = settings.resi_date_format
    counter_length = settings.resi_counter_length

    now = datetime.now()
    current_month = now.month
    current_year = now.year

    last_pengiriman = Pengiriman.query.filter(
        Pengiriman.tgl_pickup.isnot(None),
        db.extract('month', Pengiriman.tgl_pickup) == current_month,
        db.extract('year', Pengiriman.tgl_pickup) == current_year
    ).order_by(Pengiriman.id.desc()).first()

    if last_pengiriman and last_pengiriman.nomor_resi:
        try:
            last_number_str = last_pengiriman.nomor_resi.rsplit('-', 1)[-1]
            last_num = int(last_number_str)
        except (ValueError, IndexError):
            last_num = 0
    else:
        last_num = 0

    new_num = last_num + 1
    settings.resi_last_number = new_num
    db.session.commit()

    date_part = now.strftime(date_format)
    number_part = str(new_num).zfill(counter_length)
    return f"{prefix}{date_part}-{number_part}"


def generate_barcode(resi):
    """
    Generate barcode untuk nomor resi.
    Menyimpan file di static/barcodes/[resi].png
    Mengembalikan path relatif: 'barcodes/[resi].png'
    """
    # Gunakan path absolut untuk menghindari error di PythonAnywhere
    base_dir = os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(base_dir, 'static', 'barcodes')

    # Buat folder jika belum ada
    os.makedirs(folder, exist_ok=True)

    try:
        # Generate barcode CODE128
        code128 = barcode.get('code128', str(resi), writer=ImageWriter())
        filepath = os.path.join(folder, str(resi))
        code128.save(filepath)

        # Kembalikan path relatif untuk database
        return f'barcodes/{resi}.png'
    except Exception as e:
        print(f"Gagal generate barcode untuk {resi}: {e}")
        return None


def hitung_total(berat, tarif, ppn, asuransi, biaya_packing):
    # asuransi sekarang adalah "Disc %" tetapi nilainya nominal uang (Rp)
    return (berat * tarif) + ppn  + biaya_packing - asuransi


def export_to_excel(query, export_folder=None):
    """
    Export data pengiriman ke Excel.
    Jika export_folder tidak diberikan, gunakan folder 'exports' di direktori yang sama.
    """
    data = []
    for p in query:
        pengirim = p.pengirim
        penerima = p.penerima

        data.append({
            'Nama Pengirim': pengirim.nama if pengirim else '',
            'Perusahaan Pengirim': pengirim.perusahaan if pengirim else '',
            'Alamat Pengirim': pengirim.alamat if pengirim else '',
            'No Telp Pengirim': pengirim.no_telp if pengirim else '',
            'Kota Pengirim': pengirim.kode_kota if pengirim else '',
            'Nama Penerima': penerima.nama if penerima else '',
            'Perusahaan Penerima': penerima.perusahaan if penerima else '',
            'Alamat Penerima': penerima.alamat if penerima else '',
            'No Telp Penerima': penerima.no_telp if penerima else '',
            'Kota Penerima': penerima.kode_kota if penerima else '',
            'Tgl Pickup': p.tgl_pickup.strftime('%Y-%m-%d') if p.tgl_pickup else '',
            'Kota Asal': p.kota_asal,
            'Kota Tujuan': p.kota_tujuan,
            'Jenis Barang': p.jenis_barang,
            'Koli': p.jumlah_koli,
            'Kilo': p.berat_kg,
            'Tarif/kg': p.tarif_per_kg,
            'PPN': p.ppn,
            'Biaya Packing': p.biaya_packing,
            'Disc (%)': p.asuransi,
            'Total Biaya': p.total_biaya,
            'Metode Pembayaran': p.metode_pembayaran,
            'Keterangan': p.keterangan or '',
            'Petugas Pickup': p.petugas_pickup or '',
            'No Resi': p.nomor_resi,
            'Status': p.status
        })

    if not data:
        raise ValueError("Tidak ada data untuk diekspor.")

    df = pd.DataFrame(data)

    # Tentukan folder export
    if export_folder is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        export_folder = os.path.join(base_dir, 'exports')

    os.makedirs(export_folder, exist_ok=True)
    print(f"📁 Folder exports: {export_folder}")

    filename = f'pengiriman_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    path = os.path.join(export_folder, filename)
    print(f"📄 Menyimpan file ke: {path}")

    try:
        df.to_excel(path, index=False, engine='openpyxl')
        print(f"✅ File berhasil disimpan: {path}")
    except Exception as e:
        print(f"❌ Gagal menyimpan file: {e}")
        raise

    if not os.path.exists(path):
        raise FileNotFoundError(f"File tidak ditemukan: {path}")

    return path


def import_from_excel(file_path):
    df = pd.read_excel(file_path)
    df.columns = [str(col).strip().lower() for col in df.columns]

    col_map = {
        'no_resi': ['no resi', 'nomor resi', 'resi', 'no. resi'],
        'tgl_pickup': ['tgl pickup', 'tanggal pickup', 'tgl pick up', 'tanggal', 'tgl_pickup'],
        'nama_pengirim': ['nama pengirim', 'pengirim', 'nama_pengirim'],
        'perusahaan_pengirim': ['perusahaan pengirim', 'perusahaan_pengirim'],
        'alamat_pengirim': ['alamat pengirim', 'alamat_pengirim'],
        'kota_pengirim': ['kota pengirim', 'kota_pengirim', 'kota asal'],
        'no_telp_pengirim': ['no telp pengirim', 'telp pengirim', 'no_telp_pengirim'],
        'nama_penerima': ['nama penerima', 'penerima', 'nama_penerima'],
        'perusahaan_penerima': ['perusahaan penerima', 'perusahaan_penerima'],
        'alamat_penerima': ['alamat penerima', 'alamat_penerima'],
        'kota_penerima': ['kota penerima', 'kota_penerima', 'kota tujuan'],
        'no_telp_penerima': ['no telp penerima', 'telp penerima', 'no_telp_penerima'],
        'kota_asal': ['kota asal', 'kota_asal'],
        'kota_tujuan': ['kota tujuan', 'kota_tujuan'],
        'jenis_barang': ['jenis barang', 'jenis_barang'],
        'koli': ['koli', 'jumlah koli', 'koli barang'],
        'kilo': ['kilo', 'berat', 'berat (kg)', 'kilo barang'],
        'tarif_per_kg': ['tarif/kg', 'tarif per kg', 'tarif_per_kg'],
        'ppn': ['ppn'],
        'biaya_packing': ['biaya packing', 'packing', 'biaya_packing'],
        'metode_pembayaran': ['metode pembayaran', 'pembayaran', 'metode_pembayaran'],
        'keterangan': ['keterangan', 'keterangan barang'],
        'petugas_pickup': ['petugas pickup', 'petugas_pickup'],
        'jenis_service': ['jenis service', 'service', 'jenis_service']
    }

    def find_col(keys):
        for key in keys:
            if key in df.columns:
                return key
        return None

    col_found = {}
    for col, aliases in col_map.items():
        found = find_col(aliases)
        col_found[col] = found

    required = ['nama_pengirim', 'nama_penerima', 'tgl_pickup', 'kilo', 'tarif_per_kg', 'koli']
    missing = [r for r in required if not col_found[r]]
    if missing:
        raise ValueError(f"Kolom wajib tidak ditemukan: {', '.join(missing)}. Pastikan nama kolom sesuai contoh.")

    rows_added = 0
    for idx, row in df.iterrows():
        try:
            nama_pengirim = str(row[col_found['nama_pengirim']]).strip()
            if not nama_pengirim or nama_pengirim == 'nan':
                continue
            pengirim = Pelanggan.query.filter_by(nama=nama_pengirim).first()
            if not pengirim:
                pengirim = Pelanggan(
                    tipe='pengirim',
                    nama=nama_pengirim,
                    perusahaan=str(row.get(col_found.get('perusahaan_pengirim', ''), '')).strip() if col_found.get('perusahaan_pengirim') else '',
                    alamat=str(row.get(col_found.get('alamat_pengirim', ''), '')).strip() if col_found.get('alamat_pengirim') else '',
                    no_telp=str(row.get(col_found.get('no_telp_pengirim', ''), '')).strip() if col_found.get('no_telp_pengirim') else '',
                    kode_kota=str(row.get(col_found.get('kota_pengirim', ''), '')).strip() if col_found.get('kota_pengirim') else ''
                )
                db.session.add(pengirim)
                db.session.flush()

            nama_penerima = str(row[col_found['nama_penerima']]).strip()
            if not nama_penerima or nama_penerima == 'nan':
                continue
            penerima = Pelanggan.query.filter_by(nama=nama_penerima).first()
            if not penerima:
                penerima = Pelanggan(
                    tipe='penerima',
                    nama=nama_penerima,
                    perusahaan=str(row.get(col_found.get('perusahaan_penerima', ''), '')).strip() if col_found.get('perusahaan_penerima') else '',
                    alamat=str(row.get(col_found.get('alamat_penerima', ''), '')).strip() if col_found.get('alamat_penerima') else '',
                    no_telp=str(row.get(col_found.get('no_telp_penerima', ''), '')).strip() if col_found.get('no_telp_penerima') else '',
                    kode_kota=str(row.get(col_found.get('kota_penerima', ''), '')).strip() if col_found.get('kota_penerima') else ''
                )
                db.session.add(penerima)
                db.session.flush()

            resi_val = row.get(col_found.get('no_resi')) if col_found.get('no_resi') else None
            if not resi_val or pd.isna(resi_val) or str(resi_val).strip() == '':
                resi = generate_resi_number()
            else:
                resi = str(resi_val).strip()
            if Pengiriman.query.filter_by(nomor_resi=resi).first():
                continue

            tgl_str = str(row[col_found['tgl_pickup']]).strip()
            try:
                tgl_pickup = pd.to_datetime(tgl_str, format='%m-%d-%Y').date()
            except ValueError:
                tgl_pickup = pd.to_datetime(tgl_str, dayfirst=False).date()

            berat = float(row[col_found['kilo']])
            tarif = float(row[col_found['tarif_per_kg']])
            ppn = float(row.get(col_found['ppn'], 0)) if col_found['ppn'] and not pd.isna(row[col_found['ppn']]) else 0.0
            biaya_packing = float(row.get(col_found['biaya_packing'], 0)) if col_found['biaya_packing'] and not pd.isna(row[col_found['biaya_packing']]) else 0.0
            total = (berat * tarif) + ppn + biaya_packing

            koli = int(row[col_found['koli']])
            jenis_barang_val = str(row.get(col_found['jenis_barang'], 'paket')).strip().lower() if col_found['jenis_barang'] else 'paket'
            if jenis_barang_val not in ['paket', 'dokumen']:
                jenis_barang_val = 'paket'

            kota_asal_val = str(row.get(col_found['kota_asal'], '')).strip() if col_found['kota_asal'] else ''
            kota_tujuan_val = str(row.get(col_found['kota_tujuan'], '')).strip() if col_found['kota_tujuan'] else ''

            metode = str(row.get(col_found['metode_pembayaran'], 'cash')).strip().lower() if col_found['metode_pembayaran'] else 'cash'
            if metode not in ['cash', 'credit']:
                metode = 'cash'

            keterangan_val = str(row.get(col_found['keterangan'], '')).strip() if col_found['keterangan'] else ''
            petugas_val = str(row.get(col_found['petugas_pickup'], '')).strip() if col_found['petugas_pickup'] else ''
            jenis_service_val = str(row.get(col_found['jenis_service'], 'regular')).strip().lower() if col_found['jenis_service'] else 'regular'
            if jenis_service_val not in ['regular', 'express']:
                jenis_service_val = 'regular'

            # === BUAT BARCODE ===
            try:
                barcode_path = generate_barcode(resi)
                if not barcode_path:
                    barcode_path = ''
            except Exception as e:
                print(f"Gagal buat barcode untuk resi {resi}: {e}")
                barcode_path = ''

            pengiriman = Pengiriman(
                nomor_resi=resi,
                barcode_image=barcode_path,
                kota_asal=kota_asal_val,
                kota_tujuan=kota_tujuan_val,
                tgl_pickup=tgl_pickup,
                petugas_pickup=petugas_val,
                pengirim_id=pengirim.id,
                penerima_id=penerima.id,
                jenis_service=jenis_service_val,
                jenis_barang=jenis_barang_val,
                jumlah_koli=koli,
                berat_kg=berat,
                tarif_per_kg=tarif,
                ppn=ppn,
                asuransi=0,
                biaya_packing=biaya_packing,
                total_biaya=total,
                metode_pembayaran=metode,
                keterangan=keterangan_val
            )
            db.session.add(pengiriman)
            rows_added += 1
        except Exception as e:
            print(f"Error pada baris {idx}: {e}")
            continue

    db.session.commit()
    return rows_added


def import_biaya_from_excel(file_path):
    df = pd.read_excel(file_path)
    df.columns = [str(col).strip().lower() for col in df.columns]

    col_map = {
        'tanggal': ['tanggal', 'tgl', 'date'],
        'jenis': ['jenis', 'kategori', 'type'],
        'keterangan': ['keterangan', 'deskripsi', 'ket'],
        'jumlah': ['jumlah', 'biaya', 'amount', 'total']
    }

    def find_col(keys):
        for key in keys:
            if key in df.columns:
                return key
        return None

    col_found = {}
    for col, aliases in col_map.items():
        found = find_col(aliases)
        col_found[col] = found

    if not col_found['tanggal'] or not col_found['jumlah']:
        raise ValueError("Kolom 'Tanggal' dan 'Jumlah' wajib ada.")

    rows_added = 0
    for idx, row in df.iterrows():
        try:
            tgl_str = str(row[col_found['tanggal']]).strip()
            try:
                tgl = pd.to_datetime(tgl_str, format='%m-%d-%Y').date()
            except ValueError:
                tgl = pd.to_datetime(tgl_str, dayfirst=False).date()

            jumlah = float(row[col_found['jumlah']])
            jenis_val = str(row.get(col_found['jenis'], '')).strip() if col_found.get('jenis') and not pd.isna(row[col_found['jenis']]) else ''
            keterangan_val = str(row.get(col_found['keterangan'], '')).strip() if col_found.get('keterangan') and not pd.isna(row[col_found['keterangan']]) else ''

            biaya = BiayaOperasional(
                tanggal=tgl,
                jenis=jenis_val,
                keterangan=keterangan_val,
                jumlah=jumlah
            )
            db.session.add(biaya)
            rows_added += 1
        except Exception as e:
            print(f"Error pada baris {idx}: {e}")
            continue

    db.session.commit()
    return rows_added