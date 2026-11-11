from decimal import Decimal, ROUND_HALF_UP

import base64
import binascii
import json
import math
import re
import struct
import uuid
import zlib

import nh3


MAX_TEXT_ELEMENTS = 1000
MAX_STROKES = 5000
MAX_POINTS_PER_STROKE = 5000
MAX_TOTAL_POINTS = 120_000
MAX_FILLS = 5000
MAX_FILL_IMAGE_BYTES = 750_000
MAX_FILL_PIXELS = 6_000_000
MAX_HTML_LENGTH = 50_000
MAX_CONTENT_BYTES = 2 * 1024 * 1024
ALLOWED_TAGS = {
    'p', 'div', 'br', 'span', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li',
}
COLOR_PATTERN = re.compile(
    r'^(?:#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?|'
    r'rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)|'
    r'rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(0|1|0?\.\d+)\s*\))$',
    re.IGNORECASE,
)
FONT_SIZE_PATTERN = re.compile(r'^(\d+(?:\.\d+)?)px$', re.IGNORECASE)
STYLE_PATTERN = re.compile(r'\s*([a-z-]+)\s*:\s*([^;]+)\s*', re.IGNORECASE)


def _sanitize_style(style):
    sanitized = []
    for declaration in style.split(';'):
        match = STYLE_PATTERN.fullmatch(declaration)
        if not match:
            continue
        name = match.group(1).lower()
        value = match.group(2).strip()
        lowered = value.lower()
        color_match = COLOR_PATTERN.fullmatch(value) if name == 'color' else None
        if color_match:
            rgb_values = [channel for channel in color_match.groups() if channel is not None][:3]
            if not rgb_values or all(int(channel) <= 255 for channel in rgb_values):
                sanitized.append(f'color: {value}')
        elif name == 'font-size':
            size_match = FONT_SIZE_PATTERN.fullmatch(value)
            if size_match and 8 <= float(size_match.group(1)) <= 96:
                sanitized.append(f'font-size: {float(size_match.group(1)):g}px')
        elif name == 'text-align' and lowered in {'left', 'center', 'right'}:
            sanitized.append(f'text-align: {lowered}')
        elif name == 'font-family' and lowered in {'arial', '"arial"', "'arial'"}:
            sanitized.append('font-family: Arial')
    return '; '.join(sanitized)


def _clean_text_html(value):
    def filter_attribute(tag, name, attr_value):
        if tag not in ALLOWED_TAGS:
            return None
        if name == 'style':
            return _sanitize_style(attr_value) or None
        return attr_value

    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes={'*': {'style'}},
        url_schemes=set(),
        strip_comments=True,
        clean_content_tags={'script', 'style', 'iframe', 'object'},
        link_rel=None,
        filter_style_properties={'color', 'font-size', 'text-align', 'font-family'},
        attribute_filter=filter_attribute,
    )


def validate_text(element):
    html = element.get('html')
    if not isinstance(html, str):
        raise ValueError('O campo html de um bloco de texto deve ser uma string.')
    sanitized_html = _clean_text_html(html)
    if len(sanitized_html) > MAX_HTML_LENGTH:
        raise ValueError('O HTML de cada bloco deve ter no máximo 50.000 caracteres.')
    return sanitized_html


def validate_stroke(element):
    points = element.get('points')
    if not isinstance(points, list) or not 2 <= len(points) <= MAX_POINTS_PER_STROKE * 2 or len(points) % 2:
        raise ValueError('Cada traço deve ter entre 1 e 5.000 pontos completos.')

    normalized_points = []
    for coordinate in points:
        if (
            not isinstance(coordinate, (int, float))
            or isinstance(coordinate, bool)
            or coordinate < 0
            or coordinate > 20_000
            or not math.isfinite(coordinate)
        ):
            raise ValueError('As coordenadas do traço devem ser números finitos entre 0 e 20.000.')
        normalized_points.append(float(Decimal(str(coordinate)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)))

    color = element.get('color')
    if color != 'auto' and (not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color)):
        raise ValueError('A cor do traço deve ser Automática ou um hexadecimal #rrggbb.')

    width = element.get('width')
    if not isinstance(width, int) or isinstance(width, bool) or not 1 <= width <= 40:
        raise ValueError('A espessura do traço deve ser um inteiro entre 1 e 40.')

    return {
        'points': normalized_points,
        'color': color,
        'width': width,
    }


def validate_fill(element):
    image = element.get('image')
    prefix = 'data:image/png;base64,'
    if not isinstance(image, str) or not image.startswith(prefix):
        raise ValueError('A imagem de preenchimento deve ser um PNG válido.')
    try:
        image_bytes = base64.b64decode(image[len(prefix):], validate=True)
    except (binascii.Error, ValueError):
        raise ValueError('A imagem de preenchimento deve ser um PNG válido.') from None
    if len(image_bytes) > MAX_FILL_IMAGE_BYTES or not image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('A imagem de preenchimento excede o limite permitido ou não é um PNG.')

    width = height = None
    has_image_data = False
    offset = 8
    while offset + 12 <= len(image_bytes):
        chunk_length = struct.unpack_from('>I', image_bytes, offset)[0]
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(image_bytes):
            raise ValueError('A imagem de preenchimento está corrompida.')
        chunk_type = image_bytes[offset + 4:offset + 8]
        chunk_data = image_bytes[offset + 8:offset + 8 + chunk_length]
        expected_crc = struct.unpack_from('>I', image_bytes, offset + 8 + chunk_length)[0]
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            raise ValueError('A imagem de preenchimento está corrompida.')
        if offset == 8:
            if chunk_type != b'IHDR' or chunk_length != 13:
                raise ValueError('A imagem de preenchimento está corrompida.')
            width, height, depth, color_type, compression, filtering, interlace = struct.unpack(
                '>IIBBBBB',
                chunk_data,
            )
            if (depth, color_type, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                raise ValueError('O formato da imagem de preenchimento não é compatível.')
        elif chunk_type == b'IDAT':
            has_image_data = True
        elif chunk_type == b'IEND':
            if chunk_length != 0 or chunk_end != len(image_bytes):
                raise ValueError('A imagem de preenchimento está corrompida.')
            break
        offset = chunk_end
    else:
        raise ValueError('A imagem de preenchimento está corrompida.')

    if not has_image_data or width != element.get('w') or height != element.get('h'):
        raise ValueError('As dimensões da imagem de preenchimento são inválidas.')
    if width * height > MAX_FILL_PIXELS:
        raise ValueError('A imagem de preenchimento excede o limite de pixels.')

    color = element.get('color')
    if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('A cor do preenchimento deve ser hexadecimal #rrggbb.')
    return {'image': image, 'color': color.lower()}


VALIDATORS = {
    'text': validate_text,
    'stroke': validate_stroke,
    'fill': validate_fill,
}


def validate_page_content(content):
    if content == {}:
        content = {'schema': 1, 'elements': []}
    if (
        not isinstance(content, dict)
        or type(content.get('schema')) is not int
        or content.get('schema') != 1
    ):
        raise ValueError('O conteúdo da página deve usar schema 1.')
    elements = content.get('elements')
    if not isinstance(elements, list):
        raise ValueError('O campo elements deve ser uma lista.')

    sanitized_elements = []
    seen_ids = set()
    text_count = 0
    stroke_count = 0
    fill_count = 0
    total_points = 0
    for element in elements:
        if not isinstance(element, dict):
            raise ValueError('Cada bloco deve ser um objeto JSON.')
        element_id = element.get('id')
        try:
            parsed_id = uuid.UUID(element_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Cada bloco deve ter um identificador UUID válido.') from None
        if parsed_id.version != 4 or not isinstance(element_id, str) or str(parsed_id) != element_id.lower():
            raise ValueError('Cada bloco deve ter um identificador UUID v4 válido.')
        if parsed_id in seen_ids:
            raise ValueError('Os identificadores dos blocos não podem se repetir.')
        seen_ids.add(parsed_id)

        element_type = element.get('type')
        if not isinstance(element_type, str):
            raise ValueError('O tipo do bloco deve ser uma string.')
        validator = VALIDATORS.get(element_type)
        if validator is None:
            raise ValueError(f'Tipo de bloco desconhecido: {element_type}.')

        values = {}
        fields = [('z', 0, 100_000)]
        if element_type == 'text':
            text_count += 1
            if text_count > MAX_TEXT_ELEMENTS:
                raise ValueError('A página pode ter no máximo 1.000 blocos de texto.')
            fields = [
                ('x', 0, 20_000),
                ('y', 0, 20_000),
                ('w', 80, 2_000),
                *fields,
            ]
        elif element_type == 'stroke':
            stroke_count += 1
            if stroke_count > MAX_STROKES:
                raise ValueError('A página pode ter no máximo 5.000 traços.')
        elif element_type == 'fill':
            fill_count += 1
            if fill_count > MAX_FILLS:
                raise ValueError('A página pode ter no máximo 5.000 preenchimentos.')
            fields = [
                ('x', 0, 20_000),
                ('y', 0, 20_000),
                ('w', 1, 20_000),
                ('h', 1, 20_000),
                *fields,
            ]
        for field, minimum, maximum in fields:
            value = element.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
                raise ValueError(f'O campo {field} deve ser um inteiro entre {minimum} e {maximum}.')
            values[field] = value

        validated = validator(element)
        if element_type == 'fill' and (
            values['x'] + values['w'] > 20_000 or values['y'] + values['h'] > 20_000
        ):
            raise ValueError('As coordenadas do preenchimento devem ficar entre 0 e 20.000.')
        if element_type == 'stroke':
            total_points += len(validated['points']) // 2
            if total_points > MAX_TOTAL_POINTS:
                raise ValueError('A página pode ter no máximo 120.000 pontos de traço.')

        sanitized_elements.append({
            'id': str(parsed_id),
            'type': element_type,
            **values,
            **({'html': validated} if element_type == 'text' else validated),
        })

    normalized = {'schema': 1, 'elements': sanitized_elements}
    if len(json.dumps(normalized, ensure_ascii=False).encode('utf-8')) > MAX_CONTENT_BYTES:
        raise ValueError('O conteúdo excede o limite de 2 MB.')
    return normalized
