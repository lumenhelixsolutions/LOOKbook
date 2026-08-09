const express = require('express');
const { db } = require('../db');
const router = express.Router();

// List looks
router.get('/', (req, res) => {
  const looks = db.prepare('SELECT * FROM looks ORDER BY updated_at DESC').all();
  res.json(looks);
});

// Create look
router.post('/', (req, res) => {
  const { title, description, image_url, tags } = req.body;
  if (!title) return res.status(400).json({ error: 'Title is required' });
  const result = db.prepare(
    'INSERT INTO looks (title, description, image_url, tags) VALUES (?, ?, ?, ?)'
  ).run(title, description || null, image_url || null, tags || null);
  const look = db.prepare('SELECT * FROM looks WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json(look);
});

// Get look
router.get('/:id', (req, res) => {
  const look = db.prepare('SELECT * FROM looks WHERE id = ?').get(Number(req.params.id));
  if (!look) return res.status(404).json({ error: 'Look not found' });
  res.json(look);
});

// Update look
router.put('/:id', (req, res) => {
  const { title, description, image_url, tags } = req.body;
  if (!title) return res.status(400).json({ error: 'Title is required' });
  const id = Number(req.params.id);
  const existing = db.prepare('SELECT * FROM looks WHERE id = ?').get(id);
  if (!existing) return res.status(404).json({ error: 'Look not found' });
  db.prepare(
    'UPDATE looks SET title = ?, description = ?, image_url = ?, tags = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
  ).run(title, description || null, image_url || null, tags || null, id);
  const look = db.prepare('SELECT * FROM looks WHERE id = ?').get(id);
  res.json(look);
});

// Delete look
router.delete('/:id', (req, res) => {
  const id = Number(req.params.id);
  const existing = db.prepare('SELECT * FROM looks WHERE id = ?').get(id);
  if (!existing) return res.status(404).json({ error: 'Look not found' });
  db.prepare('DELETE FROM looks WHERE id = ?').run(id);
  res.status(204).send();
});

// List comments for a look
router.get('/:id/comments', (req, res) => {
  const lookId = Number(req.params.id);
  const look = db.prepare('SELECT * FROM looks WHERE id = ?').get(lookId);
  if (!look) return res.status(404).json({ error: 'Look not found' });
  const comments = db.prepare('SELECT * FROM comments WHERE look_id = ? ORDER BY created_at DESC').all(lookId);
  res.json(comments);
});

// Add comment to look
router.post('/:id/comments', (req, res) => {
  const lookId = Number(req.params.id);
  const { author, body } = req.body;
  if (!author || !body) return res.status(400).json({ error: 'Author and body are required' });
  const look = db.prepare('SELECT * FROM looks WHERE id = ?').get(lookId);
  if (!look) return res.status(404).json({ error: 'Look not found' });
  const result = db.prepare(
    'INSERT INTO comments (look_id, author, body) VALUES (?, ?, ?)'
  ).run(lookId, author, body);
  const comment = db.prepare('SELECT * FROM comments WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json(comment);
});

// Resolve comment
router.patch('/:lookId/comments/:commentId/resolve', (req, res) => {
  const commentId = Number(req.params.commentId);
  const comment = db.prepare('SELECT * FROM comments WHERE id = ?').get(commentId);
  if (!comment) return res.status(404).json({ error: 'Comment not found' });
  db.prepare('UPDATE comments SET resolved = 1 WHERE id = ?').run(commentId);
  const updated = db.prepare('SELECT * FROM comments WHERE id = ?').get(commentId);
  res.json(updated);
});

// Delete comment
router.delete('/:lookId/comments/:commentId', (req, res) => {
  const commentId = Number(req.params.commentId);
  const comment = db.prepare('SELECT * FROM comments WHERE id = ?').get(commentId);
  if (!comment) return res.status(404).json({ error: 'Comment not found' });
  db.prepare('DELETE FROM comments WHERE id = ?').run(commentId);
  res.status(204).send();
});

module.exports = router;
