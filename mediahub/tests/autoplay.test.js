import test from 'node:test';
import assert from 'node:assert/strict';
import { createAutoplay } from '../src/lib/playback/autoplay.js';

function fixture() {
  const video = Object.assign(new EventTarget(), { paused: false, seeking: false, ended: false, readyState: 4 });
  const timers = new Map();
  let serial = 0, next = 0, remaining = 10;
  const controller = createAutoplay(video, {
    onNext: () => next++, onTick: (n) => remaining = n,
    schedule: (fn) => { timers.set(++serial, fn); return serial; },
    cancel: (id) => timers.delete(id)
  });
  return { video, controller, timers, get next() { return next; }, get remaining() { return remaining; },
    event: (name) => video.dispatchEvent(new Event(name)),
    tick: () => [...timers.values()].forEach((fn) => fn()) };
}

test('pausing freezes the countdown and playing resumes the remaining time', () => {
  const f = fixture();
  f.controller.setEnabled(true);
  f.tick(); f.tick();
  f.video.paused = true; f.event('pause');
  for (let i = 0; i < 20; i++) f.tick();
  assert.equal(f.remaining, 8); assert.equal(f.next, 0);
  f.video.paused = false; f.event('playing');
  for (let i = 0; i < 8; i++) f.tick();
  assert.equal(f.next, 1);
});

test('buffering and seeking suspend autoplay until playback is ready', () => {
  const f = fixture(); f.controller.setEnabled(true); f.tick();
  f.video.readyState = 2; f.event('waiting'); f.tick();
  assert.equal(f.remaining, 9);
  f.video.readyState = 4; f.event('playing'); f.tick();
  assert.equal(f.remaining, 8);
  f.video.seeking = true; f.event('seeking'); f.tick();
  f.video.seeking = false; f.event('seeked'); f.tick();
  assert.equal(f.remaining, 7);
});

test('ended, play-now and an already queued timer can only advance once', () => {
  const f = fixture(); f.controller.setEnabled(true);
  const queued = [...f.timers.values()][0];
  f.controller.advance(); f.controller.advance(); queued();
  assert.equal(f.next, 1); assert.equal(f.timers.size, 0);
});

test('cancelling or leaving the credits resets and stops the countdown', () => {
  const f = fixture(); f.controller.setEnabled(true); f.tick();
  f.controller.setEnabled(false); f.tick();
  assert.equal(f.remaining, 10); assert.equal(f.next, 0);
  f.controller.setEnabled(true); f.tick(); assert.equal(f.remaining, 9);
});

test('destroy prevents callbacks, including queued timers and media events', () => {
  const f = fixture(); f.controller.setEnabled(true);
  const queued = [...f.timers.values()][0];
  f.controller.destroy(); queued(); f.event('playing'); f.controller.advance();
  assert.equal(f.next, 0); assert.equal(f.timers.size, 0);
});

test('a paused video never starts a timer even when the next card appears', () => {
  const f = fixture(); f.video.paused = true; f.controller.setEnabled(true);
  assert.equal(f.timers.size, 0);
});
