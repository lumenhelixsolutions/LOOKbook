const express = require('express');
const { db } = require('../db');
const router = express.Router();

const VALID_STATUSES = ['draft', 'review', 'approved', 'published'];
const STATUS_FLOW = {
  draft: ['review'],
  review: ['approved'],
  approved: ['published'],
  published: []
};

// List collections with look count
router.get('/', (req, res) => {
  const collections = db.prepare(`
    SELECT c.*,
      (SELECT COUNT(*) FROM collection_looks cl WHERE cl.collection_id = c.id) as look_count
    FROM collections c
    ORDER BY c.updated_at DESC
  `).all();
  res.json(collections);
});

// Create collection
router.post('/', (req, res) => {
  const { title, description, season, brand, cover_look_id } = req.body;
  if (!title) return res.status(400).json({ error: 'Title is required' });
  const result = db.prepare(
    'INSERT INTO collections (title, description, season, brand, cover_look_id) VALUES (?, ?, ?, ?, ?)'
  ).run(title, description || null, season || null, brand || null, cover_look_id || null);
  const collection = db.prepare('SELECT * FROM collections WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json(collection);
});

// Get collection with ordered looks
router.get('/:id', (req, res) => {
  const id = Number(req.params.id);
  const collection = db.prepare('SELECT * FROM collections WHERE id = ?').get(id);
  if (!collection) return res.status(404).json({ error: 'Collection not found' });
  const looks = db.prepare(`
    SELECT l.*, cl.order_index
    FROM looks l
    JOIN collection_looks cl ON l.id = cl.look_id
    WHERE cl.collection_id = ?
    ORDER BY cl.order_index ASC, l.id ASC
  `).all(id);
  res.json({ ...collection, looks });
});

// Update collection
router.put('/:id', (req, res) => {
  const id = Number(req.params.id);
  const { title, description, season, brand, cover_look_id } = req.body;
  const existing = db.prepare('SELECT * FROM collections WHERE id = ?').get(id);
  if (!existing) return res.status(404).json({ error: 'Collection not found' });
  if (existing.status === 'published') {
    return res.status(403).json({ error: 'Published collections are read-only' });
  }
  if (!title) return res.status(400).json({ error: 'Title is required' });
  db.prepare(
    'UPDATE collections SET title = ?, description = ?, season = ?, brand = ?, cover_look_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
  ).run(title, description || null, season || null, brand || null, cover_look_id || null, id);
  const collection = db.prepare('SELECT * FROM collections WHERE id = ?').get(id);
  res.json(collection);
});

// Delete collection
router.delete('/:id', (req, res) => {
  const id = Number(req.params.id);
  const existing = db.prepare('SELECT * FROM collections WHERE id = ?').get(id);
  if (!existing) return res.status(404).json({ error: 'Collection not found' });
  db.prepare('DELETE FROM collections WHERE id = ?').run(id);
  res.status(204).send();
});

// Add look to collection
router.post('/:id/looks', (req, res) => {
  const collectionId = Number(req.params.id);
  const { look_id } = req.body;
  if (!look_id) return res.status(400).json({ error: 'look_id is required' });
  const collection = db.prepare('SELECT * FROM collections WHERE id = ?').get(collectionId);
  if (!collection) return res.status(404).json({ error: 'Collection not found' });
  if (collection.status === 'published') {
    return res.status(403).json({ error: 'Published collections are read-only' });
  }
  const look = db.prepare('SELECT * FROM looks WHERE id = ?').get(Number(look_id));
  if (!look) return res.status(404).json({ error: 'Look not found' });
  const existing = db.prepare('SELECT * FROM collection_looks WHERE collection_id = ? AND look_id = ?').get(collectionId, look_id);
  if (existing) return res.status(409).json({ error: 'Look already in collection' });
  const maxOrder = db.prepare('SELECT COALESCE(MAX(order_index), -1) as max_order FROM collection_looks WHERE collection_id = ?').get(collectionId);
  db.prepare('INSERT INTO collection_looks (collection_id, look_id, order_index) VALUES (?, ?, ?)')
    .run(collectionId, look_id, maxOrder.max_order + 1);
  res.status(201).json({ collection_id: collectionId, look_id, order_index: maxOrder.max_order + 1 });
});

// Reorder looks in collection
router.put('/:id/looks/reorder', (req, res) => {
  const collectionId = Number(req.params.id);
  const { look_ids } = req.body;
  if (!Array.isArray(look_ids)) return res.status(400).json({ error: 'look_ids array is required' });
  const collection = db.prepare('SELECT * FROM collections WHERE id = ?').get(collectionId);
  if (!collection) return res.status(404).json({ error: 'Collection not found' });
  if (collection.status === 'published') {
    return res.status(403).json({ error: 'Published collections are read-only' });
  }
  const update = db.prepare('UPDATE collection_looks SET order_index = ? WHERE collection_id = ? AND look_id = ?');
  look_ids.forEach((lookId, index) => {
    update.run(index, collectionId, lookId);
  });
  const looks = db.prepare(`
    SELECT l.*, cl.order_index
    FROM looks l
    JOIN collection_looks cl ON l.id = cl.look_id
    WHERE cl.collection_id = ?
    ORDER BY cl.order_index ASC, l.id ASC
  `).all(collectionId);
  res.json(looks);
});

// Remove look from collection
router.delete('/:id/looks/:lookId', (req, res) => {
  const collectionId = Number(req.params.id);
  const lookId = Number(req.params.lookId);
  const collection = db.prepare('SELECT * FROM collections WHERE id = ?').get(collectionId);
  if (!collection) return res.status(404).json({ error: 'Collection not found' });
  if (collection.status === 'published') {
    return res.status(403).json({ error: 'Published collections are read-only' });
  }
  const existing = db.prepare('SELECT * FROM collection_looks WHERE collection_id = ? AND look_id = ?').get(collectionId, lookId);
  if (!existing) return res.status(404).json({ error: 'Look not in collection' });
  db.prepare('DELETE FROM collection_looks WHERE collection_id = ? AND look_id = ?').run(collectionId, lookId);
  res.status(204).send();
});

// Update status workflow
router.patch('/:id/status', (req, res) => {
  const id = Number(req.params.id);
  const { status, force } = req.body;
  if (!VALID_STATUSES.includes(status)) {
    return res.status(400).json({ error: 'Invalid status' });
  }
  const collection = db.prepare('SELECT * FROM collections WHERE id = ?').get(id);
  if (!collection) return res.status(404).json({ error: 'Collection not found' });
  if (collection.status === status) {
    return res.json(collection);
  }
  const allowed = STATUS_FLOW[collection.status] || [];
  if (!allowed.includes(status) && !force) {
    return res.status(400).json({ error: `Invalid transition from ${collection.status} to ${status}` });
  }
  db.prepare('UPDATE collections SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?').run(status, id);
  const updated = db.prepare('SELECT * FROM collections WHERE id = ?').get(id);
  res.json(updated);
});

module.exports = router;
