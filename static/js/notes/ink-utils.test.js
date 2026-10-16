'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const ink = require('./ink-utils.js');

test('simplify preserves endpoints and removes near-collinear points', function () {
    const points = [0, 0, 1, 0.1, 2, 0, 3, 0];
    const simplified = ink.simplify(points, 0.5);

    assert.deepEqual(simplified, [0, 0, 3, 0]);
});

test('bounds returns the exact extent, including a single point', function () {
    assert.deepEqual(ink.bounds([3, 7, 11, 2, 5, 14]), {
        minX: 3,
        minY: 2,
        maxX: 11,
        maxY: 14,
    });
    assert.deepEqual(ink.bounds([6, 9]), {
        minX: 6,
        minY: 9,
        maxX: 6,
        maxY: 9,
    });
});

test('hit test detects nearby, distant, and single-point strokes', function () {
    const stroke = {
        id: 'stroke',
        type: 'stroke',
        points: [0, 10, 100, 10],
        color: 'auto',
        width: 4,
        z: 1,
    };
    const dot = { ...stroke, points: [10, 10] };

    assert.equal(ink.hitTestStroke(stroke, 50, 12, 0), true);
    assert.equal(ink.hitTestStroke(stroke, 50, 20, 0), false);
    assert.equal(ink.hitTestStroke(dot, 11.5, 10, 0), true);
    assert.equal(ink.hitTestStroke(dot, 20, 10, 0), false);
});

test('capsule eraser splits a line and erases a single-point stroke', function () {
    const pieces = ink.cutPolyline(
        [0, 10, 100, 10],
        { x: 50, y: 0 },
        { x: 50, y: 20 },
        5,
    );

    assert.deepEqual(pieces, [[0, 10, 45, 10], [55, 10, 100, 10]]);
    assert.deepEqual(
        ink.cutPolyline([50, 10], { x: 50, y: 0 }, { x: 50, y: 20 }, 5),
        [],
    );
});
