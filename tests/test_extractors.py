import io,json,zipfile
from app.services.indexer import extract_text,code_chunks,_document_chunks

def test_document_chunking():
    text=('## Architecture\nalpha beta gamma\n'*300).strip(); chunks=_document_chunks(text,max_chars=500,overlap=50)
    assert len(chunks)>2 and all(c.content.strip() for c in chunks)

def test_python_symbol_chunking():
    chunks,symbols,edges=code_chunks('''import json\n\nclass Worker:\n    def run(self):\n        return helper()\n\ndef helper():\n    return 1\n''','python')
    assert any(s.name=='Worker' for s in symbols) and any(s.name=='helper' for s in symbols)
    assert any(c.symbol=='Worker' for c in chunks)

def test_ipynb_extraction():
    nb={'cells':[{'cell_type':'markdown','source':['# BFS']},{'cell_type':'code','source':['print("fifo")']} ]}
    text,lang=extract_text(json.dumps(nb).encode(),'lesson.ipynb'); assert 'BFS' in text and 'fifo' in text and lang=='python'

def test_docx_extraction_minimal():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello Spartan</w:t></w:r></w:p></w:body></w:document>')
    text,_=extract_text(buf.getvalue(),'note.docx'); assert 'Hello Spartan' in text
