import os
from pypdf import PdfReader

def extract_text_with_keywords(file_path, keywords, max_pages=50):
    try:
        reader = PdfReader(file_path)
        print(f"--- Analyzing: {os.path.basename(file_path)} ---")
        
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            text = page.extract_text()
            # Check if any keyword is in the page
            if any(k in text for k in keywords):
                print(f"--- Page {i+1} ---")
                # Print context around keywords
                for k in keywords:
                    if k in text:
                        idx = text.find(k)
                        start = max(0, idx - 200)
                        end = min(len(text), idx + 200)
                        print(f"[{k}]: ...{text[start:end]}...")
                        print("-" * 20)
    except Exception as e:
        print(f"Error: {e}")

def main():
    base_path = "/Users/wenqing/Desktop/VAgent"
    files = [
        "黑龙江建龙转炉提钒技术材料--修改--2020.6.13(1).pdf",
        "铁水预处理提钒讲课稿[整理版](1).pdf"
    ]
    
    # Abnormal conditions keywords
    keywords = ["喷溅", "返干", "碳氧化", "钒收得率", "温度过高", "枪位", "氧化铁皮"]
    
    for f in files:
        full_path = os.path.join(base_path, f)
        if os.path.exists(full_path):
            extract_text_with_keywords(full_path, keywords)
        else:
            print(f"File not found: {full_path}")

if __name__ == "__main__":
    main()
