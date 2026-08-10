import streamlit as st
import pymupdf as fitz
import re
import os
import tempfile

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
st.write("อัปโหลดไฟล์ PDF คู่มือเพื่อสร้างลิงก์เชื่อมโยงให้อัตโนมัติ")

# 1. ตัวเลือกประเภทคู่มือ
doc_type = st.radio(
    "📌 เลือกประเภทคู่มือ:",
    ("OM (Owner's Manual - คู่มือการใช้รถ)", "WSM (Workshop Manual - คู่มือการซ่อม)"),
    index=0
)

# 2. ส่วนการอัปโหลดไฟล์
uploaded_file = st.file_uploader("เลือกไฟล์ PDF ต้นฉบับ", type=["pdf"])

if uploaded_file is not None:
    if st.button("▶ เริ่มสร้างลิงก์ (Start)", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in:
            tmp_in.write(uploaded_file.read())
            input_pdf_path = tmp_in.name

        output_pdf_path = input_pdf_path.replace(".pdf", "_link.pdf")

        try:
            status_text.info("กำลังเปิดไฟล์ PDF...")
            doc = fitz.open(input_pdf_path)
            total_pages = len(doc)

            # ==================== ลอจิก OM ====================
            if "OM" in doc_type:
                page_code_pattern = re.compile(r'\b([0-9]{1,2}-[0-9]{1,3})\b')

                status_text.info("🔍 Pass 1: สแกนหาเลขหน้าจากขอบบนกระดาษ (Header 45pt)...")
                page_map = {}

                for page_index in range(total_pages):
                    page = doc[page_index]
                    rect = page.rect
                    top_header_rect = fitz.Rect(0, 0, rect.width, 45)
                    header_text = page.get_text("text", clip=top_header_rect)

                    matches = page_code_pattern.findall(header_text)
                    for code in matches:
                        if code not in page_map: page_map[code] = page_index

                    progress_bar.progress(int((page_index / total_pages) * 40))

                status_text.info("🔗 Pass 2: วาดลิงก์คำอ้างอิงและตารางทั้งหมด...")
                total_links = 0
                ref_pattern = re.compile(r'(?:→\s*)?(?:หน้า\s*)?\b([0-9]{1,2}-[0-9]{1,3})\b')

                for page_index in range(total_pages):
                    page = doc[page_index]
                    text_page = page.get_text("dict")

                    for block in text_page.get("blocks", []):
                        if "lines" not in block: continue

                        for line in block["lines"]:
                            line_rect = fitz.Rect(line["bbox"])
                            if line_rect.y1 <= 45: continue

                            line_text = "".join([span["text"] for span in line["spans"]]).strip()
                            matches = ref_pattern.finditer(line_text)

                            for match in matches:
                                target_code = match.group(1)
                                if target_code in page_map:
                                    target_page_idx = page_map[target_code]
                                    if target_page_idx == page_index: continue

                                    matched_str = match.group(0)
                                    text_instances = page.search_for(matched_str)

                                    for inst in text_instances:
                                        if inst.y1 <= 45: continue
                                        link = {
                                            "kind": fitz.LINK_GOTO,
                                            "from": inst,
                                            "page": target_page_idx
                                        }
                                        page.insert_link(link)
                                        total_links += 1

                    progress_bar.progress(int(40 + ((page_index / total_pages) * 60)))

            # ==================== ลอจิก WSM ====================
            else:
                status_text.info("กำลังสแกนหาขอบเขตสารบัญ...")
                toc_starts = []
                for i in range(total_pages):
                    text = doc[i].get_text("text")
                    if "สารบัญ" in text:
                        if not toc_starts or i > toc_starts[-1] + 2:
                            toc_starts.append(i)
                toc_starts.append(total_pages)

                status_text.info("กำลังสแกนหาเลขหน้าจริงจาก Header...")
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

                    progress_bar.progress(int((page_index / total_pages) * 40))

                status_text.info("กำลังสร้างลิงก์ลงในสารบัญ...")
                current_section_idx = 0
                in_toc = False
                toc_end_pattern = re.compile(r'([0-9]{1,3}[A-Z]+-[0-9]+)\s*$')

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
                            entry_rect = None

                            for line in block["lines"]:
                                line_text = "".join([span["text"] for span in line["spans"]]).strip()
                                line_rect = fitz.Rect(line["bbox"])

                                if entry_rect is None: entry_rect = line_rect
                                else: entry_rect = entry_rect | line_rect

                                match = toc_end_pattern.search(line_text)
                                if match:
                                    target_code = match.group(1)
                                    if target_code in page_map:
                                        possible_pages = page_map[target_code]
                                        target_page = None

                                        for p in possible_pages:
                                            if toc_starts[current_section_idx] <= p < current_section_end:
                                                target_page = p
                                                break

                                        if target_page is not None:
                                            link = {
                                                "kind": fitz.LINK_GOTO,
                                                "from": entry_rect,
                                                "page": target_page
                                            }
                                            page.insert_link(link)
                                            links_created_on_this_page += 1

                                    entry_rect = None

                    if in_toc and links_created_on_this_page == 0 and "สารบัญ" not in text:
                        in_toc = False

                    progress_bar.progress(int(40 + ((page_index / total_pages) * 60)))

            doc.save(output_pdf_path)
            doc.close()

            progress_bar.progress(100)
            status_text.success("🎉 ประมวลผลสำเร็จเรียบร้อยแล้ว!")

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
