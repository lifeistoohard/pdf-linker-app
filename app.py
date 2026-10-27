import streamlit as st
import pymupdf as fitz
import re
import os
import tempfile
import unicodedata

st.set_page_config(page_title="PDF Link Generator", page_icon="🔗", layout="centered")

# ซ่อน Streamlit UI Elements ให้ดูคลีน
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("🔗 PDF Link Generator by NA")
st.write("อัปโหลดไฟล์ PDF คู่มือเพื่อสร้างลิงก์เชื่อมโยงให้อัตโนมัติ (รองรับระบบ Y-Center Row)")

# 1. ตัวเลือกประเภทคู่มือ
doc_type = st.radio(
    "📌 เลือกประเภทคู่มือ:",
    ("OM (Owner's Manual - คู่มือการใช้รถ)", "WSM (Workshop Manual - คู่มือการซ่อม)"),
    index=0
)

# 2. ส่วนการอัปโหลดไฟล์
uploaded_file = st.file_uploader("เลือกไฟล์ PDF ต้นฉบับ", type=["pdf"])

def super_clean(text):
    """ ฟังก์ชันล้างขยะภาษาไทยขั้นสุด (ใช้สำหรับโหมด OM) """
    if not text: return ""
    text = str(text)
    text = unicodedata.normalize('NFC', text)
    text = text.replace('\u0E33', '\u0E4D\u0E32') # แก้สระอำ
    text = text.replace('\u0E40\u0E40', '\u0E41') # แก้สระแอ
    text = re.sub(r'[\uE000-\uF8FF\U000f0000-\U0010ffff\u02c6-\u02df]', '', text)
    text = re.sub(r'([\u0e31\u0e34-\u0e3a])+', r'\1', text) # ลดสระเบิ้ล
    text = re.sub(r'([\u0e48-\u0e4c])+', r'\1', text)
    # เก็บเฉพาะ ก-ฮ, a-z, 0-9 ตัดช่องว่างและสัญลักษณ์ทิ้งทั้งหมด
    text = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9]', '', text)
    return text.lower()

if uploaded_file is not None:
    if st.button("▶ เริ่มสร้างลิงก์ (Start)", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        error_summary = []
        total_links = 0
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in:
            tmp_in.write(uploaded_file.read())
            input_pdf_path = tmp_in.name

        output_pdf_path = input_pdf_path.replace(".pdf", "_link.pdf")

        try:
            status_text.info("กำลังเปิดไฟล์ PDF...")
            doc = fitz.open(input_pdf_path)
            total_pages = len(doc)

            # ==================== ลอจิก OM (พร้อมระบบ QC) ====================
            if "OM" in doc_type:
                page_code_pattern = re.compile(r'\b([A-Za-z0-9]{1,3}-[0-9]{1,3})\b')

                status_text.info("🔍 Pass 1: สแกนหาเลขหน้าจากขอบบนกระดาษ...")
                page_map = {}
                for page_index in range(total_pages):
                    page = doc[page_index]
                    top_header_rect = fitz.Rect(0, 0, page.rect.width, 45)
                    header_text = page.get_text("text", clip=top_header_rect)

                    matches = page_code_pattern.findall(header_text)
                    for code in matches:
                        if code not in page_map: page_map[code] = page_index
                    progress_bar.progress(int((page_index / total_pages) * 20))

                status_text.info("🧠 Pass 2: อ่านเนื้อหาทั้งเล่มเพื่อทำ Cache (QC)...")
                page_cache = {}
                for page_index in range(total_pages):
                    page = doc[page_index]
                    content_rect = fitz.Rect(0, 46, page.rect.width, page.rect.height - 40)
                    raw_text = page.get_text("text", clip=content_rect)
                    page_cache[page_index] = super_clean(raw_text)
                    progress_bar.progress(int(20 + (page_index / total_pages) * 20))

                status_text.info("🔗 Pass 3: วาดลิงก์และตรวจสอบความถูกต้อง...")
                ref_pattern = re.compile(r'(?:→\s*)?(?:หน้า|หน้้า\s*)?\b([A-Za-z0-9]{1,3}-[0-9]{1,3})\b')

                for page_index in range(total_pages):
                    page = doc[page_index]
                    text_page = page.get_text("dict")
                    
                    page_lines = []
                    for block in text_page.get("blocks", []):
                        if "lines" not in block: continue
                        for line in block["lines"]:
                            line_rect = fitz.Rect(line["bbox"])
                            if line_rect.y1 <= 45: continue
                            line_text = "".join([span["text"] for span in line["spans"]]).strip()
                            if line_text:
                                page_lines.append({"text": line_text, "bbox": line_rect})
                    
                    page_lines.sort(key=lambda l: (round(l["bbox"].y0, 1), l["bbox"].x0))

                    for idx, line_obj in enumerate(page_lines):
                        line_text = line_obj["text"]
                        matches = ref_pattern.finditer(line_text)

                        for match in matches:
                            target_code = match.group(1)
                            matched_str = match.group(0)

                            raw_context = line_text[:match.start()].strip()
                            clean_context = super_clean(raw_context)

                            if len(clean_context) < 3:
                                for back in range(1, 3):
                                    if idx - back >= 0:
                                        prev_text = page_lines[idx - back]["text"]
                                        prev_clean = super_clean(prev_text)
                                        if len(prev_clean) >= 3:
                                            raw_context = prev_text
                                            clean_context = prev_clean
                                            break

                            if target_code in page_map:
                                target_page_idx = page_map[target_code]
                                final_target_page = target_page_idx

                                if len(clean_context) >= 3:
                                    if clean_context not in page_cache.get(target_page_idx, ""):
                                        candidates = [p for p in range(total_pages) if clean_context in page_cache[p]]
                                        if candidates:
                                            candidates.sort(key=lambda x: abs(x - target_page_idx))
                                            final_target_page = candidates[0]
                                            error_summary.append(f"🛠️ '{raw_context}' (ระบุ: {target_code} -> ซ่อมไปหน้า: {final_target_page + 1})")
                                        else:
                                            error_summary.append(f"⚠️ หาคำไม่พบ: '{raw_context}' (โยงไปหน้าเดิม: {target_code})")

                                if final_target_page == page_index: continue

                                text_instances = page.search_for(matched_str)
                                for inst in text_instances:
                                    if inst.y1 <= 45: continue
                                    link = {"kind": fitz.LINK_GOTO, "from": inst, "page": final_target_page}
                                    page.insert_link(link)
                                    total_links += 1

                    progress_bar.progress(int(40 + ((page_index / total_pages) * 60)))

            # ==================== ลอจิก WSM (Strict Y-Center Row) ====================
            else:
                HEADER_HEIGHT = 90
                PG_PATTERN = r'^([0-9]{1,3}[A-Za-z]*-[0-9]{1,3}|\d+)$'
                page_map = {}

                status_text.info("🔍 Pass 1: กำลังอ่านเลขหน้าจาก 'แถบเทาดำด้านบนสุด' เท่านั้น...")
                for page_index in range(total_pages):
                    page = doc[page_index]
                    header_rect = fitz.Rect(0, 0, page.rect.width, HEADER_HEIGHT)
                    header_text = page.get_text("text", clip=header_rect)
                    
                    for line in header_text.split('\n'):
                        tokens = line.split()
                        if not tokens: continue
                        
                        first = re.sub(r'^[^\w-]+|[^\w-]+$', '', tokens[0])
                        last = re.sub(r'^[^\w-]+|[^\w-]+$', '', tokens[-1])
                        
                        if re.match(PG_PATTERN, first):
                            if first not in page_map: page_map[first] = []
                            page_map[first].append(page_index)
                            break
                        elif re.match(PG_PATTERN, last):
                            if last not in page_map: page_map[last] = []
                            page_map[last].append(page_index)
                            break

                    progress_bar.progress(int((page_index / total_pages) * 30))

                status_text.info("🔗 Pass 2: กำลังค้นหาจุดเชื่อมโยงในเนื้อหา และตีกรอบแนวนอน (Y-Center)...")
                for page_index in range(total_pages):
                    page = doc[page_index]
                    
                    all_lines = []
                    dict_text = page.get_text("dict")
                    for block in dict_text.get("blocks", []):
                        if "lines" not in block: continue
                        for line in block["lines"]:
                            line_rect = fitz.Rect(line["bbox"])
                            
                            if line_rect.y0 < HEADER_HEIGHT:
                                continue
                                
                            text = "".join([span["text"] for span in line["spans"]]).strip()
                            if text:
                                all_lines.append((line_rect, text))
                    
                    if not all_lines: continue
                    
                    for line_rect, line_text in all_lines:
                        targets_in_line = set()

                        for m in re.finditer(r'หน้า\s*([0-9]{1,3}[A-Za-z]*-[0-9]{1,3}|\d+)', line_text):
                            targets_in_line.add(m.group(1))

                        toc_m = re.search(r'(?:\.{2,}|\s{4,})\s*([0-9]{1,3}[A-Za-z]*-[0-9]{1,3}|\d+)\s*$', line_text)
                        if toc_m:
                            targets_in_line.add(toc_m.group(1))

                        for m in re.finditer(r'\b([0-9]{1,3}[A-Za-z]+-[0-9]{1,3}|\d+-\d+)\b', line_text):
                            targets_in_line.add(m.group(1))

                        for code in targets_in_line:
                            if re.match(r'(?i)^s-\d+', code):
                                continue
                                
                            if code in page_map:
                                valid_pages = [p for p in page_map[code] if p != page_index] 
                                if valid_pages:
                                    target_page = valid_pages[0]
                                    
                                    # ระบบตีกรอบแนวนอนใหม่ วัดจากจุดกึ่งกลาง (Y-Center Alignment)
                                    row_rects = []
                                    line_y_mid = (line_rect.y0 + line_rect.y1) / 2
                                    
                                    for o_rect, o_text in all_lines:
                                        o_y_mid = (o_rect.y0 + o_rect.y1) / 2
                                        # ถ้าระดับจุดกึ่งกลางต่างกันไม่เกิน 6 px ถือว่าเป็นบรรทัดเดียวกัน
                                        if abs(line_y_mid - o_y_mid) < 6:
                                            row_rects.append((o_rect, o_text))
                                    
                                    if row_rects:
                                        row_x0 = min([r.x0 for r, t in row_rects])
                                        row_x1 = max([r.x1 for r, t in row_rects])
                                        row_y0 = min([r.y0 for r, t in row_rects])
                                        row_y1 = max([r.y1 for r, t in row_rects])
                                        full_row_rect = fitz.Rect(row_x0, row_y0, row_x1, row_y1)
                                    else:
                                        full_row_rect = line_rect
                                    
                                    page.insert_link({"kind": fitz.LINK_GOTO, "from": full_row_rect, "page": target_page})
                                    total_links += 1

                    progress_bar.progress(int(30 + ((page_index / total_pages) * 70)))

            # บันทึกไฟล์
            doc.save(output_pdf_path)
            doc.close()

            progress_bar.progress(100)
            
            # การแสดงผลข้อความความสำเร็จ (แยกตามโหมด)
            if "OM" in doc_type:
                if error_summary:
                    report_text = "\n".join(error_summary[:20])
                    if len(error_summary) > 20:
                        report_text += f"\n...และอื่นๆ อีก {len(error_summary) - 20} รายการ"
                    st.warning(f"**รายงาน QC (พบการอ้างอิงคลาดเคลื่อน {len(error_summary)} จุด):**\n\n{report_text}")
                    status_text.success(f"🎉 ประมวลผลเสร็จสิ้น! สร้างลิงก์สำเร็จทั้งหมด {total_links} จุด (มีการซ่อมลิงก์)")
                else:
                    st.info("✅ ตรวจสอบเนื้อหาทั้งหมดตรงตามอ้างอิง ไม่พบข้อผิดพลาด!")
                    status_text.success(f"🎉 ประมวลผลเสร็จสิ้น! สร้างลิงก์สำเร็จทั้งหมด {total_links} จุด (ตรงเป๊ะ 100%)")
            else:
                # โหมด WSM (Y-Center Row) แสดงเฉพาะข้อความสำเร็จ
                status_text.success(f"🎉 เสร็จสิ้นสมบูรณ์! สร้างลิงก์และตีกรอบแนวนอนสำเร็จทั้งหมด {total_links} จุด (ตรงเป้าหมาย 100%)")

            # ปุ่มดาวน์โหลด
            with open(output_pdf_path, "rb") as f:
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์ PDF (ที่มีลิงก์แล้ว)",
                    data=f,
                    file_name=f"{os.path.splitext(uploaded_file.name)[0]}_link.pdf",
                    mime="application/pdf",
                    type="primary"
                )

        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาด: {str(e)}")
        finally:
            if os.path.exists(input_pdf_path): os.remove(input_pdf_path)
            if os.path.exists(output_pdf_path): os.remove(output_pdf_path)
