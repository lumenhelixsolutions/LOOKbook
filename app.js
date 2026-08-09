const express = require('express');
const path = require('node:path');
const methodOverride = require('method-override');
const expressLayouts = require('express-ejs-layouts');
const looksRouter = require('./routes/looks');
const collectionsRouter = require('./routes/collections');

const app = express();

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(expressLayouts);
app.set('layout', 'layout');

app.use(express.urlencoded({ extended: true }));
app.use(express.json());
app.use(methodOverride('_method'));
app.use(express.static(path.join(__dirname, 'public')));

app.use('/api/looks', looksRouter);
app.use('/api/collections', collectionsRouter);

app.get('/', (req, res) => {
  res.redirect('/looks');
});

app.get('/looks', async (req, res) => {
  const { db } = require('./db');
  const looks = db.prepare('SELECT * FROM looks ORDER BY updated_at DESC').all();
  res.render('looks', { looks });
});

app.get('/looks/new', (req, res) => {
  res.render('look-form', { look: null });
});

app.get('/looks/:id/edit', async (req, res) => {
  const { db } = require('./db');
  const look = db.prepare('SELECT * FROM looks WHERE id = ?').get(Number(req.params.id));
  if (!look) return res.status(404).send('Look not found');
  res.render('look-form', { look });
});

app.get('/looks/:id', async (req, res) => {
  const { db } = require('./db');
  const look = db.prepare('SELECT * FROM looks WHERE id = ?').get(Number(req.params.id));
  if (!look) return res.status(404).send('Look not found');
  const comments = db.prepare('SELECT * FROM comments WHERE look_id = ? ORDER BY created_at DESC').all(look.id);
  const collections = db.prepare('SELECT id, title FROM collections ORDER BY title').all();
  const inCollections = db.prepare('SELECT collection_id FROM collection_looks WHERE look_id = ?').all(look.id).map(r => r.collection_id);
  res.render('look-detail', { look, comments, collections, inCollections });
});

app.get('/collections', async (req, res) => {
  const { db } = require('./db');
  const collections = db.prepare(`
    SELECT c.*,
      (SELECT COUNT(*) FROM collection_looks cl WHERE cl.collection_id = c.id) as look_count
    FROM collections c
    ORDER BY c.updated_at DESC
  `).all();
  res.render('collections', { collections });
});

app.get('/collections/new', (req, res) => {
  const { db } = require('./db');
  const looks = db.prepare('SELECT id, title FROM looks ORDER BY title').all();
  res.render('collection-form', { collection: null, looks });
});

app.get('/collections/:id/edit', async (req, res) => {
  const { db } = require('./db');
  const collection = db.prepare('SELECT * FROM collections WHERE id = ?').get(Number(req.params.id));
  if (!collection) return res.status(404).send('Collection not found');
  const looks = db.prepare('SELECT id, title FROM looks ORDER BY title').all();
  res.render('collection-form', { collection, looks });
});

app.get('/collections/:id', async (req, res) => {
  const { db } = require('./db');
  const collection = db.prepare('SELECT * FROM collections WHERE id = ?').get(Number(req.params.id));
  if (!collection) return res.status(404).send('Collection not found');
  const looks = db.prepare(`
    SELECT l.*, cl.order_index
    FROM looks l
    JOIN collection_looks cl ON l.id = cl.look_id
    WHERE cl.collection_id = ?
    ORDER BY cl.order_index ASC, l.id ASC
  `).all(collection.id);
  const allLooks = db.prepare('SELECT id, title FROM looks ORDER BY title').all();
  res.render('collection-detail', { collection, looks, allLooks });
});

const PORT = process.env.PORT || 3000;
if (process.env.NODE_ENV !== 'test') {
  app.listen(PORT, () => {
    console.log(`lookBOOK server running on http://localhost:${PORT}`);
  });
}

module.exports = { app };
