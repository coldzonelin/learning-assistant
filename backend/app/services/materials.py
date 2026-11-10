import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from pptx import Presentation
from pypdf import PdfReader


def sections(path, file_type):
    if file_type in ('doc', 'ppt'):
        executable = shutil.which('soffice') or shutil.which('libreoffice')
        if not executable:
            raise ValueError('解析旧版 Word/PPT 需要安装 LibreOffice')
        target = 'docx' if file_type == 'doc' else 'pptx'
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory, 'profile').as_uri()
            result = subprocess.run([executable, f'-env:UserInstallation={profile}', '--headless', '--convert-to', target, '--outdir', directory, str(path)], capture_output=True, timeout=60)
            converted = Path(directory, f'{path.stem}.{target}')
            if result.returncode or not converted.exists():
                raise ValueError('旧版文件转换失败')
            return sections(converted, target)
    if file_type == 'pdf':
        return [(page.extract_text() or '', number, None) for number, page in enumerate(PdfReader(path).pages, 1)]
    if file_type == 'pptx':
        output = []
        for number, slide in enumerate(Presentation(path).slides, 1):
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    texts.append(shape.text)
                if shape.has_table:
                    texts.extend(cell.text for row in shape.table.rows for cell in row.cells)
            output.append(('\n'.join(texts), number, None))
        return output
    if file_type == 'docx':
        document = Document(path)
        text = '\n'.join(p.text for p in document.paragraphs)
        for table in document.tables:
            text += '\n' + '\n'.join('\t'.join(cell.text for cell in row.cells) for row in table.rows)
        return [(text, None, None)]
    text = Path(path).read_text(encoding='utf-8-sig')
    if file_type in ('md', 'markdown'):
        output, title, lines = [], None, []
        for line in text.splitlines():
            match = re.match(r'^#{1,6}\s+(.+)', line)
            if match:
                if lines: output.append(('\n'.join(lines), None, title))
                title, lines = match.group(1), [line]
            else: lines.append(line)
        if lines: output.append(('\n'.join(lines), None, title))
        return output
    return [(text, None, None)]


def extract(path, file_type):
    chunks = []
    for text, page, title in sections(path, file_type):
        text = text.strip()
        for offset in range(0, len(text), 2000):
            part = text[offset:offset + 2000].strip()
            if part: chunks.append((part, page, title))
    if not chunks:
        raise ValueError('文件没有可提取的文本；扫描图片需要先进行文字识别')
    return chunks
