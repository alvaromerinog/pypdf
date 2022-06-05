import io
import os
import time
from io import BytesIO
import urllib.request

import pytest

from PyPDF2 import PdfReader
from PyPDF2._reader import convert_to_int, convertToInt
from PyPDF2.constants import ImageAttributes as IA
from PyPDF2.constants import PageAttributes as PG
from PyPDF2.constants import Ressources as RES
from PyPDF2.errors import PdfReadError, PdfReadWarning
from PyPDF2.filters import _xobj_to_image

TESTS_ROOT = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_ROOT)
RESOURCE_ROOT = os.path.join(PROJECT_ROOT, "resources")


@pytest.mark.parametrize(
    ("src", "num_pages"),
    [("selenium-PyPDF2-issue-177.pdf", 1), ("pdflatex-outline.pdf", 4)],
)
def test_get_num_pages(src, num_pages):
    src = os.path.join(RESOURCE_ROOT, src)
    reader = PdfReader(src)
    assert len(reader.pages) == num_pages


@pytest.mark.parametrize(
    ("pdf_path", "expected"),
    [
        (
            os.path.join(RESOURCE_ROOT, "crazyones.pdf"),
            {
                "/CreationDate": "D:20150604133406-06'00'",
                "/Creator": " XeTeX output 2015.06.04:1334",
                "/Producer": "xdvipdfmx (20140317)",
            },
        ),
        (
            os.path.join(RESOURCE_ROOT, "metadata.pdf"),
            {
                "/CreationDate": "D:20220415093243+02'00'",
                "/ModDate": "D:20220415093243+02'00'",
                "/Creator": "pdflatex, or other tool",
                "/Producer": "Latex with hyperref, or other system",
                "/Author": "Martin Thoma",
                "/Keywords": "Some Keywords, other keywords; more keywords",
                "/Subject": "The Subject",
                "/Title": "The Title",
                "/Trapped": "/False",
                "/PTEX.Fullbanner": (
                    "This is pdfTeX, Version "
                    "3.141592653-2.6-1.40.23 (TeX Live 2021) "
                    "kpathsea version 6.3.3"
                ),
            },
        ),
    ],
    ids=["crazyones", "metadata"],
)
def test_read_metadata(pdf_path, expected):
    with open(pdf_path, "rb") as inputfile:
        reader = PdfReader(inputfile)
        with pytest.warns(PendingDeprecationWarning):
            docinfo = reader.documentInfo
        assert docinfo is not None
        metadict = dict(docinfo)
        assert metadict == expected
        docinfo.title
        docinfo.title_raw
        docinfo.author
        docinfo.author_raw
        docinfo.creator
        docinfo.creator_raw
        docinfo.producer
        docinfo.producer_raw
        docinfo.subject
        docinfo.subject_raw
        if "/Title" in metadict:
            assert metadict["/Title"] == docinfo.title


@pytest.mark.parametrize(
    "src",
    [
        (os.path.join(RESOURCE_ROOT, "crazyones.pdf")),
        (os.path.join(RESOURCE_ROOT, "commented.pdf")),
    ],
)
def test_get_annotations(src):
    reader = PdfReader(src)

    for page in reader.pages:
        if PG.ANNOTS in page:
            for annot in page[PG.ANNOTS]:
                subtype = annot.get_object()[IA.SUBTYPE]
                if subtype == "/Text":
                    annot.get_object()[PG.CONTENTS]


@pytest.mark.parametrize(
    "src",
    [
        (os.path.join(RESOURCE_ROOT, "attachment.pdf")),
        (os.path.join(RESOURCE_ROOT, "crazyones.pdf")),
    ],
)
def test_get_attachments(src):
    reader = PdfReader(src)

    attachments = {}
    for i in range(len(reader.pages)):
        page = reader.pages[i]
        if PG.ANNOTS in page:
            for annotation in page[PG.ANNOTS]:
                annotobj = annotation.get_object()
                if annotobj[IA.SUBTYPE] == "/FileAttachment":
                    fileobj = annotobj["/FS"]
                    attachments[fileobj["/F"]] = fileobj["/EF"]["/F"].get_data()
    return attachments


@pytest.mark.parametrize(
    ("src", "outline_elements"),
    [
        (os.path.join(RESOURCE_ROOT, "pdflatex-outline.pdf"), 9),
        (os.path.join(RESOURCE_ROOT, "crazyones.pdf"), 0),
    ],
)
def test_get_outlines(src, outline_elements):
    reader = PdfReader(src)
    outlines = reader._get_outlines()
    assert len(outlines) == outline_elements


@pytest.mark.parametrize(
    ("src", "nb_images"),
    [
        ("pdflatex-outline.pdf", 0),
        ("crazyones.pdf", 0),
        ("git.pdf", 1),
        ("imagemagick-lzw.pdf", 1),
        ("imagemagick-ASCII85Decode.pdf", 1),
        ("imagemagick-CCITTFaxDecode.pdf", 1),
    ],
)
def test_get_images(src, nb_images):
    src = os.path.join(RESOURCE_ROOT, src)
    reader = PdfReader(src)

    with pytest.raises(TypeError):
        page = reader.pages["0"]

    page = reader.pages[-1]
    page = reader.pages[0]

    images_extracted = []

    if RES.XOBJECT in page[PG.RESOURCES]:
        xObject = page[PG.RESOURCES][RES.XOBJECT].get_object()

        for obj in xObject:
            if xObject[obj][IA.SUBTYPE] == "/Image":
                extension, byte_stream = _xobj_to_image(xObject[obj])
                if extension is not None:
                    filename = obj[1:] + ".png"
                    with open(filename, "wb") as img:
                        img.write(byte_stream)
                    images_extracted.append(filename)

    assert len(images_extracted) == nb_images

    # Cleanup
    for filepath in images_extracted:
        os.remove(filepath)


@pytest.mark.parametrize(
    ("strict", "with_prev_0", "startx_correction", "should_fail"),
    [
        (True, False, -1, False),  # all nominal => no fail
        (True, True, -1, True),  # Prev=0 => fail expected
        (False, False, -1, False),
        (False, True, -1, False),  # Prev =0 => no strict so tolerant
        (True, False, 0, True),  # error on startxref, in strict => fail expected
        (True, True, 0, True),
        (
            False,
            False,
            0,
            False,
        ),  # error on startxref, but no strict => xref rebuilt,no fail
        (False, True, 0, False),
    ],
)
def test_get_images_raw(strict, with_prev_0, startx_correction, should_fail):
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        b"5 0 obj << /Pages 1 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << %s/Root 5 0 R /Size 6 >>\n"
        b"startxref %d\n"
        b"%%%%EOF"
    )
    pdf_data = pdf_data % (
        pdf_data.find(b"1 0 obj"),
        pdf_data.find(b"2 0 obj"),
        pdf_data.find(b"3 0 obj"),
        pdf_data.find(b"4 0 obj"),
        pdf_data.find(b"5 0 obj"),
        b"/Prev 0 " if with_prev_0 else b"",
        # startx_correction should be -1 due to double % at the beginning indiducing an error on startxref computation
        pdf_data.find(b"xref") + startx_correction,
    )
    pdf_stream = io.BytesIO(pdf_data)
    if should_fail:
        with pytest.raises(PdfReadError) as exc:
            with pytest.warns(PdfReadWarning):
                PdfReader(pdf_stream, strict=strict)
        assert exc.type == PdfReadError
        if startx_correction == -1:
            assert (
                exc.value.args[0]
                == "/Prev=0 in the trailer (try opening with strict=False)"
            )
    else:
        with pytest.warns(PdfReadWarning):
            PdfReader(pdf_stream, strict=strict)


def test_issue297():
    path = os.path.join(RESOURCE_ROOT, "issue-297.pdf")
    with pytest.raises(PdfReadError) as exc:
        with pytest.warns(PdfReadWarning):
            reader = PdfReader(path, strict=True)
    assert "Broken xref table" in exc.value.args[0]
    with pytest.warns(PdfReadWarning):
        reader = PdfReader(path, strict=False)
    reader.pages[0]


@pytest.mark.parametrize(
    ("pdffile", "password", "should_fail"),
    [
        ("encrypted-file.pdf", "test", False),
        ("encrypted-file.pdf", "qwerty", True),
        ("encrypted-file.pdf", b"qwerty", True),
    ],
)
def test_get_page_of_encrypted_file(pdffile, password, should_fail):
    """
    Check if we can read a page of an encrypted file.

    This is a regression test for issue 327:
    IndexError for get_page() of decrypted file
    """
    path = os.path.join(RESOURCE_ROOT, pdffile)
    if should_fail:
        with pytest.raises(PdfReadError):
            PdfReader(path, password=password)
    else:
        PdfReader(path, password=password).pages[0]


@pytest.mark.parametrize(
    ("pdffile", "password"),
    [
        ("crazyones-encrypted-256.pdf", "password"),
    ],
)
def test_get_page_of_encrypted_file_new_algorithm(pdffile, password):
    """
    Check if we can read a page of an encrypted file.

    This is a regression test for issue 327:
    IndexError for get_page() of decrypted file
    """
    path = os.path.join(RESOURCE_ROOT, pdffile)
    with pytest.raises(NotImplementedError) as exc:
        PdfReader(path, password=password).pages[0]
    assert (
        exc.value.args[0]
        == "only algorithm code 1 and 2 are supported. This PDF uses code 5"
    )


@pytest.mark.parametrize(
    ("src", "expected", "expected_get_fields"),
    [
        (
            "form.pdf",
            {"foo": ""},
            {"foo": {"/DV": "", "/FT": "/Tx", "/T": "foo", "/V": ""}},
        ),
        (
            "form_acrobatReader.pdf",
            {"foo": "Bar"},
            {"foo": {"/DV": "", "/FT": "/Tx", "/T": "foo", "/V": "Bar"}},
        ),
        (
            "form_evince.pdf",
            {"foo": "bar"},
            {"foo": {"/DV": "", "/FT": "/Tx", "/T": "foo", "/V": "bar"}},
        ),
        (
            "crazyones.pdf",
            {},
            None,
        ),
    ],
)
def test_get_form(src, expected, expected_get_fields):
    """Check if we can read out form data."""
    src = os.path.join(RESOURCE_ROOT, src)
    reader = PdfReader(src)
    fields = reader.get_form_text_fields()
    assert fields == expected

    fields = reader.get_fields()
    assert fields == expected_get_fields
    if fields:
        for field in fields.values():
            # Just access the attributes
            [
                field.field_type,
                field.parent,
                field.kids,
                field.name,
                field.alternate_name,
                field.mapping_name,
                field.flags,
                field.value,
                field.default_value,
                field.additional_actions,
            ]


@pytest.mark.parametrize(
    ("src", "page_nb"),
    [
        ("form.pdf", 0),
        ("pdflatex-outline.pdf", 2),
    ],
)
def test_get_page_number(src, page_nb):
    src = os.path.join(RESOURCE_ROOT, src)
    reader = PdfReader(src)
    page = reader.pages[page_nb]
    assert reader.get_page_number(page) == page_nb


@pytest.mark.parametrize(
    ("src", "expected"),
    [("form.pdf", None), ("AutoCad_Simple.pdf", "/SinglePage")],
)
def test_get_page_layout(src, expected):
    src = os.path.join(RESOURCE_ROOT, src)
    reader = PdfReader(src)
    assert reader.page_layout == expected


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("form.pdf", "/UseNone"),
        ("crazyones.pdf", None),
    ],
)
def test_get_page_mode(src, expected):
    src = os.path.join(RESOURCE_ROOT, src)
    reader = PdfReader(src)
    assert reader.page_mode == expected


def test_read_empty():
    with pytest.raises(PdfReadError) as exc:
        PdfReader(io.BytesIO())
    assert exc.value.args[0] == "Cannot read an empty file"


def test_read_malformed_header():
    with pytest.raises(PdfReadError) as exc:
        PdfReader(io.BytesIO(b"foo"), strict=True)
    assert exc.value.args[0] == "PDF starts with 'foo', but '%PDF-' expected"


def test_read_malformed_body():
    with pytest.raises(PdfReadError) as exc:
        PdfReader(io.BytesIO(b"%PDF-"), strict=True)
    assert exc.value.args[0] == "Could not read malformed PDF file"


def test_read_prev_0_trailer():
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        b"5 0 obj << /Pages 1 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << %s/Root 5 0 R /Size 6 >>\n"
        b"startxref %d\n"
        b"%%%%EOF"
    )
    with_prev_0 = True
    pdf_data = pdf_data % (
        pdf_data.find(b"1 0 obj"),
        pdf_data.find(b"2 0 obj"),
        pdf_data.find(b"3 0 obj"),
        pdf_data.find(b"4 0 obj"),
        pdf_data.find(b"5 0 obj"),
        b"/Prev 0 " if with_prev_0 else b"",
        pdf_data.find(b"xref") - 1,
    )
    pdf_stream = io.BytesIO(pdf_data)
    with pytest.raises(PdfReadError) as exc:
        with pytest.warns(PdfReadWarning):
            PdfReader(pdf_stream, strict=True)
    assert exc.value.args[0] == "/Prev=0 in the trailer (try opening with strict=False)"


def test_read_missing_startxref():
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        b"5 0 obj << /Pages 1 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << /Root 5 0 R /Size 6 >>\n"
        # b"startxref %d\n"
        b"%%%%EOF"
    )
    pdf_data = pdf_data % (
        pdf_data.find(b"1 0 obj"),
        pdf_data.find(b"2 0 obj"),
        pdf_data.find(b"3 0 obj"),
        pdf_data.find(b"4 0 obj"),
        pdf_data.find(b"5 0 obj"),
        # pdf_data.find(b"xref") - 1,
    )
    pdf_stream = io.BytesIO(pdf_data)
    with pytest.raises(PdfReadError) as exc:
        PdfReader(pdf_stream, strict=True)
    assert exc.value.args[0] == "startxref not found"


def test_read_unknown_zero_pages():
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        # Pages 0 0 is the key point:
        b"5 0 obj << /Pages 0 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << /Root 5 1 R /Size 6 >>\n"
        b"startxref %d\n"
        b"%%%%EOF"
    )
    pdf_data = pdf_data % (
        pdf_data.find(b"1 0 obj"),
        pdf_data.find(b"2 0 obj"),
        pdf_data.find(b"3 0 obj"),
        pdf_data.find(b"4 0 obj"),
        pdf_data.find(b"5 0 obj"),
        pdf_data.find(b"xref") - 1,
    )
    pdf_stream = io.BytesIO(pdf_data)
    with pytest.warns(PdfReadWarning):
        reader = PdfReader(pdf_stream, strict=True)
    with pytest.raises(PdfReadError) as exc:
        with pytest.warns(PdfReadWarning):
            len(reader.pages)

    assert exc.value.args[0] == "Could not find object."
    with pytest.warns(PdfReadWarning):
        reader = PdfReader(pdf_stream, strict=False)
    with pytest.raises(AttributeError) as exc:
        with pytest.warns(PdfReadWarning):
            len(reader.pages)
    assert exc.value.args[0] == "'NoneType' object has no attribute 'get_object'"


def test_read_encrypted_without_decryption():
    src = os.path.join(RESOURCE_ROOT, "libreoffice-writer-password.pdf")
    reader = PdfReader(src)
    with pytest.raises(PdfReadError) as exc:
        len(reader.pages)
    assert exc.value.args[0] == "File has not been decrypted"


def test_get_destination_page_number():
    src = os.path.join(RESOURCE_ROOT, "pdflatex-outline.pdf")
    reader = PdfReader(src)
    outlines = reader._get_outlines()
    for outline in outlines:
        if not isinstance(outline, list):
            reader.get_destination_page_number(outline)


def test_do_not_get_stuck_on_large_files_without_start_xref():
    """Tests for the absence of a DoS bug, where a large file without an startxref mark
    would cause the library to hang for minutes to hours"""
    start_time = time.time()
    broken_stream = BytesIO(b"\0" * 5 * 1000 * 1000)
    with pytest.raises(PdfReadError):
        PdfReader(broken_stream)
    parse_duration = time.time() - start_time
    # parsing is expected take less than a second on a modern cpu, but include a large
    # tolerance to account for busy or slow systems
    assert parse_duration < 60


def test_PdfReaderDecryptWhenNoID():
    """
    Decrypt an encrypted file that's missing the 'ID' value in its
    trailer.
    https://github.com/mstamy2/PyPDF2/issues/608
    """

    with open(
        os.path.join(RESOURCE_ROOT, "encrypted_doc_no_id.pdf"), "rb"
    ) as inputfile:
        ipdf = PdfReader(inputfile)
        ipdf.decrypt("")
        assert ipdf.metadata == {"/Producer": "European Patent Office"}


def test_reader_properties():
    reader = PdfReader(os.path.join(RESOURCE_ROOT, "crazyones.pdf"))
    assert reader.outlines == []
    assert len(reader.pages) == 1
    assert reader.page_layout is None
    assert reader.page_mode is None
    assert reader.is_encrypted is False


@pytest.mark.parametrize(
    "strict",
    [(True), (False)],
)
def test_issue604(strict):
    """Test with invalid destinations"""  # todo
    with open(os.path.join(RESOURCE_ROOT, "issue-604.pdf"), "rb") as f:
        pdf = None
        bookmarks = None
        if strict:
            with pytest.raises(PdfReadError) as exc:
                pdf = PdfReader(f, strict=strict)
                with pytest.warns(PdfReadWarning):
                    bookmarks = pdf._get_outlines()
            if "Unknown Destination" not in exc.value.args[0]:
                raise Exception("Expected exception not raised")
            return  # bookmarks not correct
        else:
            pdf = PdfReader(f, strict=strict)
            with pytest.warns(PdfReadWarning):
                bookmarks = pdf._get_outlines()

        def get_dest_pages(x):
            # print(x)
            if isinstance(x, list):
                r = [get_dest_pages(y) for y in x]
                return r
            else:
                return pdf.get_destination_page_number(x) + 1

        out = []
        for (
            b
        ) in bookmarks:  # b can be destination or a list:preferred to just print them
            out.append(get_dest_pages(b))
    # print(out)


def test_decode_permissions():
    reader = PdfReader(os.path.join(RESOURCE_ROOT, "crazyones.pdf"))
    base = {
        "accessability": False,
        "annotations": False,
        "assemble": False,
        "copy": False,
        "forms": False,
        "modify": False,
        "print_high_quality": False,
        "print": False,
    }

    print_ = base.copy()
    print_["print"] = True
    assert reader.decode_permissions(4) == print_

    modify = base.copy()
    modify["modify"] = True
    assert reader.decode_permissions(8) == modify


def test_VirtualList():
    pdf_path = os.path.join(RESOURCE_ROOT, "crazyones.pdf")
    reader = PdfReader(pdf_path)

    # Test if getting as slice throws an error
    assert len(reader.pages[:]) == 1


def test_convert_to_int():
    assert convert_to_int(b"\x01", 8) == 1


def test_convert_to_int_error():
    with pytest.raises(PdfReadError) as exc:
        convert_to_int(b"256", 16)
    assert exc.value.args[0] == "invalid size in convert_to_int"


def test_convertToInt_deprecated():
    msg = (
        "convertToInt is deprecated and will be removed in PyPDF2 3.0.0. "
        "Use convert_to_int instead."
    )
    with pytest.warns(
        PendingDeprecationWarning,
        match=msg,
    ):
        assert convertToInt(b"\x01", 8) == 1


def test_iss925():
    reader = PdfReader(BytesIO(urllib.request.urlopen(
        "https://github.com/py-pdf/PyPDF2/files/8796328/1.pdf").read()))

    for page_sliced in reader.pages:
        page_object = page_sliced.get_object()
        # Extracts the PDF's Annots (Annotations and Commenting):
        annots = page_object.get("/Annots")
        if annots is not None:
            for annot in annots:
                annot.get_object()