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
st.write("อัปโหลดไฟล์ PDF คู่มือเพื่อสร้างลิงก์เชื่อมโยงให้อัตโนมัติ (พร้อมระบบ QC)")

# 1. ตัวเลือกประเภทคู่มือ
doc_type = st.radio(
    "📌 เลือกประเภทคู่มือ:",
    ("OM (Owner's Manual - คู่มือการใช้รถ)", "WSM (Workshop Manual - คู่มือการซ่อม)"),
    index=0
)

# 2. ส่วนการอัปโหลดไฟล์
uploaded_file = st.file_uploader("เลือกไฟล์ PDF ต้นฉบับ", type=["pdf"])

def super_clean(text):
    """ ฟังก์ชันล้างขยะภาษาไทยขั้นสุด เพื่อใช้เทียบเนื้อหา QC """
    if not text: return ""
    text = str(text)
    text = unicodedata.normalize('NFC', text)
    text = text.replace('\u0E33', '\u0E4D\u0E32') # แก้สระอำ
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
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in:
            tmp_in.write(uploaded_file.read())
            input_pdf_path = tmp_in.name

        output_pdf_path = input_pdf_path.replace(".pdf", "_link.pdf")

        try:
            status_text.info("กำลังเปิดไฟล์ PDF...")
            doc = fitz.open(input_pdf_path)
            total_pages = len(doc)

            # ==================== ลอจิก OM (อัปเกรดระบบ QC) ====================
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
                total_links = 0
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

                            # ดึงข้อความบริบทฝั่งซ้ายเพื่อทำ QC
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

                                # 🛡️ ระบบ QC Content
                                if len(clean_context) >= 3:
                                    if clean_context not in page_cache.get(target_page_idx, ""):
                                        # ควานหาหน้าที่ถูกต้อง
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

            # ==================== ลอจิก WSM (อัปเกรดระบบ QC) ====================
            else:
                status_text.info("กำลังสแกนหาขอบเขตสารบัญ...")
                toc_starts = []
                for i in range(total_pages):
                    text = doc[i].get_text("text")
                    if "สารบัญ" in text:
                        if not toc_starts or i > toc_starts[-1] + 2:
                            toc_starts.append(i)
                toc_starts.append(total_pages)

                status_text.info("🔍 Pass 1: สแกนหาเลขหน้าจริงจาก Header...")
                page_map = {}
                page_code_pattern = re.compile(r'\b([0-9]{1,3}[A-Z]+-[0-9]+)\b')

                for page_index in range(total_pages):
                    page = doc[page_index]
                    header_rect = fitz.Rect(0, 0, page.rect.width, 120)
                    header_text = page.get_text("text", clip=header_rect)
                    
                    matches = page_code_pattern.findall(header_text)
                    for match in matches:
                        if match not in page_map: page_map[match] = []
                        page_map[match].append(page_index)
                    progress_bar.progress(int((page_index / total_pages) * 30))

                status_text.info("🧠 Pass 2: อ่านเนื้อหาเพื่อทำ Cache (QC)...")
                page_cache = {}
                for page_index in range(total_pages):
                    top_area = fitz.Rect(0, 0, doc[page_index].rect.width, doc[page_index].rect.height) # กวาดทั้งหน้าเพื่อความชัวร์
                    raw_text = doc[page_index].get_text("text", clip=top_area)
                    page_cache[page_index] = super_clean(raw_text)
                    progress_bar.progress(int(30 + ((page_index / total_pages) * 30)))

                status_text.info("🔗 Pass 3: สร้างลิงก์ลงในสารบัญและตรวจทาน...")
                current_section_idx = 0
                in_toc = False

                for page_index in range(total_pages):
                    if current_section_idx < len(toc_starts) - 2:
                        if page_index >= toc_starts[current_section_idx + 1]:
                            current_section_idx += 1

                    current_section_end = toc_starts[current_section_idx + 1]
                    page = doc[page_index]
                    text = page.get_text("text")

                    if "สารบัญ" in text: in_toc = True
                    links_created_on_this_page = 0

                    if in_toc:
                        dict_text = page.get_text("dict")
                        for block in dict_text.get("blocks", []):
                            if "lines" not in block: continue

                            for line in block["lines"]:
                                line_text = "".join([span["text"] for span in line["spans"]]).strip()
                                line_rect = fitz.Rect(line["bbox"])

                                # จับแพทเทิร์นสารบัญ: หัวข้อ ..... หน้า X-YY
                                match = re.search(r'^(.*?)(?:\.{2,}|\s{3,})\s*([0-9]{1,3}[A-Za-z]+-[0-9]+|\d+)\s*$', line_text)
                                if not match: continue

                                topic_text = match.group(1).strip()
                                target_code = match.group(2).strip()
                                if len(topic_text) < 2: continue

                                clean_topic = super_clean(topic_text)
                                target_page = None

                                # หาจาก Map ก่อน
                                if target_code in page_map:
                                    for p in page_map[target_code]:
                                        if toc_starts[current_section_idx] <= p < current_section_end:
                                            target_page = p
                                            break

                                # 🛡️ ระบบ QC Content สำหรับ WSM
                                final_target_page = None
                                candidates = []
                                for p in range(toc_starts[current_section_idx], current_section_end):
                                    if clean_topic in page_cache[p]:
                                        candidates.append(p)
                                    else:
                                        # Fallback สำหรับรหัส DTC
                                        temp_en = clean_topic.replace('dtc', '')
                                        codes = re.findall(r'[a-z0-9]{5,}', temp_en)
                                        for c in codes:
                                            if c in page_cache[p]:
                                                candidates.append(p)
                                                break

                                if not candidates:
                                    if target_page is not None:
                                        final_target_page = target_page
                                        error_summary.append(f"⚠️ หาเนื้อหาไม่พบ: '{topic_text}' (โยงไปตามสารบัญ: {target_page + 1})")
                                else:
                                    if target_page is not None:
                                        candidates.sort(key=lambda x: abs(x - target_page))
                                        final_target_page = candidates[0]
                                        if final_target_page != target_page:
                                            error_summary.append(f"🛠️ '{topic_text}' (สารบัญบอก: {target_code} -> ซ่อมไปหน้า: {final_target_page + 1})")
                                    else:
                                        final_target_page = candidates[0]
                                        error_summary.append(f"🔍 กู้คืนรหัสผิด: '{topic_text}' (โยงไปหน้า: {final_target_page + 1})")

                                if final_target_page is not None:
                                    link = {"kind": fitz.LINK_GOTO, "from": line_rect, "page": final_target_page}
                                    page.insert_link(link)
                                    links_created_on_this_page += 1

                    if in_toc and links_created_on_this_page == 0 and "สารบัญ" not in text:
                        in_toc = False

                    progress_bar.progress(int(60 + ((page_index / total_pages) * 40)))

            # บันทึกไฟล์
            doc.save(output_pdf_path)
            doc.close()

            progress_bar.progress(100)
            status_text.success("🎉 ประมวลผลและตรวจสอบ QC เสร็จสมบูรณ์แล้ว!")

            # แสดง Report ถ้าพบข้อผิดพลาด
            if error_summary:
                report_text = "\n".join(error_summary[:20])
                if len(error_summary) > 20:
                    report_text += f"\n...และอื่นๆ อีก {len(error_summary) - 20} รายการ"
                st.warning(f"**รายงาน QC (พบการอ้างอิงผิดพลาดและซ่อมแซมแล้ว {len(error_summary)} จุด):**\n\n{report_text}")
            else:
                st.info("✅ ตรวจสอบเนื้อหาทั้งหมดตรงตามหน้าสารบัญ ไม่พบข้อผิดพลาด!")

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
