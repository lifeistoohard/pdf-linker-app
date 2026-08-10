import streamlit as st
import pymupdf as fitz
import re
import os
import tempfile

st.set_page_config(page_title="PDF Link Generator", page_icon="🔗", layout="centered")

st.title("🔗 PDF Link Generator by NA")
st.write("อัปโหลดไฟล์ PDF เพื่อสร้างลิงก์เชื่อมโยงในหน้าสารบัญให้อัตโนมัติ")

# 1. ส่วนการอัปโหลดไฟล์
uploaded_file = st.file_uploader("เลือกไฟล์ PDF ต้นฉบับ", type=["pdf"])

if uploaded_file is not None:
    if st.button("▶ เริ่มสร้างลิงก์ (Start)", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # สร้าง Temp File เพื่อประมวลผล
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in:
            tmp_in.write(uploaded_file.read())
            input_pdf_path = tmp_out_path = tmp_in.name

        output_pdf_path = input_pdf_path.replace(".pdf", "_link.pdf")

        try:
            status_text.info("กำลังเปิดไฟล์ PDF...")
            doc = fitz.open(input_pdf_path)
            total_pages = len(doc)

            # 1. หาขอบเขตของสารบัญ
            toc_starts = []
            for i in range(total_pages):
                text = doc[i].get_text("text")
                if "สารบัญ" in text:
                    if not toc_starts or i > toc_starts[-1] + 2:
                        toc_starts.append(i)
            toc_starts.append(total_pages)

            # 2. Auto Page Mapping (Header)
            status_text.info("กำลังสแกนหาเลขหน้าจริงจาก Header...")
            page_map = {}
            page_code_pattern = re.compile(r'\b([0-9]{1,3}[A-Z]+-[0-9]+)\b')

            for page_index in range(total_pages):
                page = doc[page_index]
                header_rect = fitz.Rect(0, 0, page.rect.width, 120)
                header_text = page.get_text("text", clip=header_rect)
                
                matches = page_code_pattern.findall(header_text)
                for match in matches:
                    if match not in page_map:
                        page_map[match] = []
                    page_map[match].append(page_index)

                progress_bar.progress(int((page_index / total_pages) * 40))

            # 3. วาดลิงก์
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

                if "สารบัญ" in text:
                    in_toc = True

                links_created_on_this_page = 0

                if in_toc:
                    dict_text = page.get_text("dict")
                    for block in dict_text.get("blocks", []):
                        if "lines" not in block: continue
                        entry_rect = None

                        for line in block["lines"]:
                            line_text = "".join([span["text"] for span in line["spans"]]).strip()
                            line_rect = fitz.Rect(line["bbox"])

                            if entry_rect is None:
                                entry_rect = line_rect
                            else:
                                entry_rect = entry_rect | line_rect

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
            status_text.success("🎉 ประมวลผลสำเร็จ!")

            # 4. ปุ่มดาวน์โหลดไฟล์กลับลงเครื่อง
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
            # ลบไฟล์ Temp หลังทำงานเสร็จ
            if os.path.exists(input_pdf_path): os.remove(input_pdf_path)
            if os.path.exists(output_pdf_path): os.remove(output_pdf_path)