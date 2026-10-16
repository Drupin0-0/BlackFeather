(function (root, factory) {
    'use strict';

    const utils = factory();
    root.NotesInkUtils = utils;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = utils;
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    function validPoints(points) {
        return Array.isArray(points) &&
            points.length >= 2 &&
            points.length <= 10_000 &&
            points.length % 2 === 0 &&
            points.every(function (coordinate) {
                return Number.isFinite(coordinate) && coordinate >= 0 && coordinate <= 20_000;
            });
    }

    function validStroke(stroke) {
        return Boolean(stroke) &&
            stroke.type === 'stroke' &&
            Number.isInteger(stroke.z) && stroke.z >= 0 && stroke.z <= 100_000 &&
            Number.isInteger(stroke.width) && stroke.width >= 1 && stroke.width <= 40 &&
            (stroke.color === 'auto' || (
                typeof stroke.color === 'string' && stroke.color.length === 7 && /^#[0-9a-fA-F]{6}$/.test(stroke.color)
            )) &&
            validPoints(stroke.points);
    }

    function pointDistanceSquared(points, index, startIndex, endIndex) {
        const x = points[index];
        const y = points[index + 1];
        const startX = points[startIndex];
        const startY = points[startIndex + 1];
        const endX = points[endIndex];
        const endY = points[endIndex + 1];
        const deltaX = endX - startX;
        const deltaY = endY - startY;
        if (deltaX === 0 && deltaY === 0) {
            const offsetX = x - startX;
            const offsetY = y - startY;
            return offsetX * offsetX + offsetY * offsetY;
        }
        const projection = Math.max(0, Math.min(1, (
            (x - startX) * deltaX + (y - startY) * deltaY
        ) / (deltaX * deltaX + deltaY * deltaY)));
        const nearestX = startX + projection * deltaX;
        const nearestY = startY + projection * deltaY;
        const offsetX = x - nearestX;
        const offsetY = y - nearestY;
        return offsetX * offsetX + offsetY * offsetY;
    }

    function simplify(points, tolerance) {
        if (!validPoints(points) || !Number.isFinite(tolerance) || tolerance < 0) {
            return [];
        }
        const pointCount = points.length / 2;
        if (pointCount <= 2) {
            return points.slice();
        }

        const keep = new Uint8Array(pointCount);
        keep[0] = 1;
        keep[pointCount - 1] = 1;
        const pending = [[0, pointCount - 1]];
        const toleranceSquared = tolerance * tolerance;
        while (pending.length) {
            const segment = pending.pop();
            const start = segment[0] * 2;
            const end = segment[1] * 2;
            let farthestIndex = -1;
            let farthestDistance = toleranceSquared;
            for (let index = segment[0] + 1; index < segment[1]; index += 1) {
                const distance = pointDistanceSquared(points, index * 2, start, end);
                if (distance > farthestDistance) {
                    farthestDistance = distance;
                    farthestIndex = index;
                }
            }
            if (farthestIndex >= 0) {
                keep[farthestIndex] = 1;
                pending.push([segment[0], farthestIndex], [farthestIndex, segment[1]]);
            }
        }

        const result = [];
        for (let index = 0; index < pointCount; index += 1) {
            if (keep[index]) {
                result.push(points[index * 2], points[index * 2 + 1]);
            }
        }
        return result;
    }

    function bounds(points) {
        if (!validPoints(points)) {
            return null;
        }
        let minX = points[0];
        let minY = points[1];
        let maxX = points[0];
        let maxY = points[1];
        for (let index = 2; index < points.length; index += 2) {
            minX = Math.min(minX, points[index]);
            minY = Math.min(minY, points[index + 1]);
            maxX = Math.max(maxX, points[index]);
            maxY = Math.max(maxY, points[index + 1]);
        }
        return { minX: minX, minY: minY, maxX: maxX, maxY: maxY };
    }

    function distanceToSegment(x, y, startX, startY, endX, endY) {
        const deltaX = endX - startX;
        const deltaY = endY - startY;
        if (deltaX === 0 && deltaY === 0) {
            return Math.hypot(x - startX, y - startY);
        }
        const projection = Math.max(0, Math.min(1, (
            (x - startX) * deltaX + (y - startY) * deltaY
        ) / (deltaX * deltaX + deltaY * deltaY)));
        return Math.hypot(x - startX - projection * deltaX, y - startY - projection * deltaY);
    }

    function segmentCircleRoots(startX, startY, endX, endY, centerX, centerY, radius) {
        const dx = endX - startX;
        const dy = endY - startY;
        const fx = startX - centerX;
        const fy = startY - centerY;
        const a = dx * dx + dy * dy;
        if (!a) {
            return [];
        }
        const b = 2 * (fx * dx + fy * dy);
        const c = fx * fx + fy * fy - radius * radius;
        const discriminant = b * b - 4 * a * c;
        if (discriminant < 0) {
            return [];
        }
        const root = Math.sqrt(discriminant);
        return [(-b - root) / (2 * a), (-b + root) / (2 * a)]
            .filter(function (value) { return value > 0 && value < 1; });
    }

    function segmentCapsuleRoots(startX, startY, endX, endY, lineStart, lineEnd, radius) {
        const lineX = lineEnd.x - lineStart.x;
        const lineY = lineEnd.y - lineStart.y;
        const lineLengthSquared = lineX * lineX + lineY * lineY;
        if (!lineLengthSquared) {
            return segmentCircleRoots(startX, startY, endX, endY, lineStart.x, lineStart.y, radius);
        }
        const roots = segmentCircleRoots(startX, startY, endX, endY, lineStart.x, lineStart.y, radius)
            .concat(segmentCircleRoots(startX, startY, endX, endY, lineEnd.x, lineEnd.y, radius));
        const directionX = endX - startX;
        const directionY = endY - startY;
        const lineLength = Math.sqrt(lineLengthSquared);
        const signedStart = (lineX * (startY - lineStart.y) - lineY * (startX - lineStart.x)) / lineLength;
        const signedDelta = (lineX * directionY - lineY * directionX) / lineLength;
        if (signedDelta) {
            [-radius, radius].forEach(function (target) {
                const t = (target - signedStart) / signedDelta;
                if (t > 0 && t < 1) {
                    const x = startX + directionX * t;
                    const y = startY + directionY * t;
                    const projection = ((x - lineStart.x) * lineX + (y - lineStart.y) * lineY) /
                        lineLengthSquared;
                    if (projection >= 0 && projection <= 1) {
                        roots.push(t);
                    }
                }
            });
        }
        return roots;
    }

    function pointSegmentDistanceSquared(point, start, end) {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        if (!dx && !dy) {
            return (point.x - start.x) ** 2 + (point.y - start.y) ** 2;
        }
        const t = Math.max(0, Math.min(1, (
            (point.x - start.x) * dx + (point.y - start.y) * dy
        ) / (dx * dx + dy * dy)));
        return (point.x - start.x - t * dx) ** 2 + (point.y - start.y - t * dy) ** 2;
    }

    function outsideCapsuleIntervals(start, end, lineStart, lineEnd, radius) {
        const roots = [0, 1].concat(
            segmentCapsuleRoots(start.x, start.y, end.x, end.y, lineStart, lineEnd, radius)
        ).sort(function (left, right) { return left - right; });
        const unique = roots.filter(function (value, index) {
            return index === 0 || Math.abs(value - roots[index - 1]) > 1e-9;
        });
        const intervals = [];
        for (let index = 0; index < unique.length - 1; index += 1) {
            const from = unique[index];
            const to = unique[index + 1];
            const middle = (from + to) / 2;
            const point = {
                x: start.x + (end.x - start.x) * middle,
                y: start.y + (end.y - start.y) * middle,
            };
            if (pointSegmentDistanceSquared(point, lineStart, lineEnd) > radius * radius) {
                intervals.push([from, to]);
            }
        }
        return intervals;
    }

    function polylineLength(points) {
        let length = 0;
        for (let index = 0; index < points.length - 2; index += 2) {
            length += Math.hypot(points[index + 2] - points[index], points[index + 3] - points[index + 1]);
        }
        return length;
    }

    function cutPolyline(points, lineStart, lineEnd, radius) {
        if (!validPoints(points) || !lineStart || !lineEnd ||
            ![lineStart.x, lineStart.y, lineEnd.x, lineEnd.y, radius].every(Number.isFinite) ||
            radius <= 0) {
            return [points.slice()];
        }
        if (points.length === 2) {
            return pointSegmentDistanceSquared(
                { x: points[0], y: points[1] }, lineStart, lineEnd
            ) <= radius * radius ? [] : [points.slice()];
        }

        const pieces = [];
        let current = [];
        function appendPointToPiece(point) {
            const previous = current.length >= 2
                ? { x: current[current.length - 2], y: current[current.length - 1] }
                : null;
            if (!previous || Math.hypot(point.x - previous.x, point.y - previous.y) > 1e-7) {
                current.push(Math.round(point.x * 10) / 10, Math.round(point.y * 10) / 10);
            }
        }
        function finishPiece() {
            if (current.length >= 4 && polylineLength(current) >= 1) {
                pieces.push(current);
            }
            current = [];
        }

        for (let index = 0; index < points.length - 2; index += 2) {
            const start = { x: points[index], y: points[index + 1] };
            const end = { x: points[index + 2], y: points[index + 3] };
            const intervals = outsideCapsuleIntervals(start, end, lineStart, lineEnd, radius);
            intervals.forEach(function (interval) {
                const from = interval[0];
                const to = interval[1];
                const pieceStart = {
                    x: start.x + (end.x - start.x) * from,
                    y: start.y + (end.y - start.y) * from,
                };
                const pieceEnd = {
                    x: start.x + (end.x - start.x) * to,
                    y: start.y + (end.y - start.y) * to,
                };
                if (from > 1e-7) {
                    finishPiece();
                }
                appendPointToPiece(pieceStart);
                appendPointToPiece(pieceEnd);
                if (to < 1 - 1e-7) {
                    finishPiece();
                }
            });
            if (intervals.length === 0) {
                finishPiece();
            }
        }
        finishPiece();
        return pieces;
    }

    function hitTestStroke(stroke, x, y, radius) {
        if (!validStroke(stroke) || !Number.isFinite(x) || !Number.isFinite(y) ||
            !Number.isFinite(radius) || radius < 0) {
            return false;
        }
        const box = bounds(stroke.points);
        const threshold = radius + stroke.width / 2;
        if (
            x < box.minX - threshold || x > box.maxX + threshold ||
            y < box.minY - threshold || y > box.maxY + threshold
        ) {
            return false;
        }
        if (stroke.points.length === 2) {
            return distanceToSegment(x, y, stroke.points[0], stroke.points[1], stroke.points[0], stroke.points[1]) <= threshold;
        }
        for (let index = 0; index < stroke.points.length - 2; index += 2) {
            if (distanceToSegment(
                x,
                y,
                stroke.points[index],
                stroke.points[index + 1],
                stroke.points[index + 2],
                stroke.points[index + 3],
            ) <= threshold) {
                return true;
            }
        }
        return false;
    }

    function formatCoordinate(value) {
        return String(Math.round(value * 10) / 10);
    }

    function pathData(points) {
        if (!validPoints(points)) {
            return '';
        }
        const count = points.length / 2;
        let data = 'M ' + formatCoordinate(points[0]) + ' ' + formatCoordinate(points[1]);
        if (count === 1) {
            return data + ' Q ' + formatCoordinate(points[0]) + ' ' + formatCoordinate(points[1]) +
                ' ' + formatCoordinate(points[0]) + ' ' + formatCoordinate(points[1]);
        }
        if (count === 2) {
            data += ' Q ' + formatCoordinate((points[0] + points[2]) / 2) + ' ' +
                formatCoordinate((points[1] + points[3]) / 2) + ' ' +
                formatCoordinate(points[2]) + ' ' + formatCoordinate(points[3]);
            return data;
        }
        for (let index = 1; index < count - 1; index += 1) {
            const x = points[index * 2];
            const y = points[index * 2 + 1];
            const nextX = points[(index + 1) * 2];
            const nextY = points[(index + 1) * 2 + 1];
            data += ' Q ' + formatCoordinate(x) + ' ' + formatCoordinate(y) + ' ' +
                formatCoordinate((x + nextX) / 2) + ' ' + formatCoordinate((y + nextY) / 2);
        }
        const lastIndex = points.length - 2;
        data += ' Q ' + formatCoordinate(points[lastIndex]) + ' ' + formatCoordinate(points[lastIndex + 1]) +
            ' ' + formatCoordinate(points[lastIndex]) + ' ' + formatCoordinate(points[lastIndex + 1]);
        return data;
    }

    return {
        bounds: bounds,
        cutPolyline: cutPolyline,
        hitTestStroke: hitTestStroke,
        pathData: pathData,
        simplify: simplify,
        validStroke: validStroke,
    };
}));
