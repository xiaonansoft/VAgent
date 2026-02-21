import os
import sys
from pypdf import PdfReader

def read_pdf_range(file_path, start_page, end_page):
    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        print(f"Total pages: {total_pages}")
        
        text = ""
        for i in range(start_page, min(end_page, total_pages)):
            print(f"--- Page {i+1} Content ---")
            page_text = reader.pages[i].extract_text()
            print(page_text)
            text += page_text + "\n"
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    target_pdf = "5.达涅利SDM自动炼钢模型四大平衡计算(2)_20260130152512.pdf"
    base_path = "/Users/wenqing/Desktop/VAgent"
    full_path = os.path.join(base_path, target_pdf)
    
    start = 2 # Start from page 3 (index 2)
    end = 15  # End at page 15
    
    read_pdf_range(full_path, start, end)
