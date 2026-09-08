"""Admitted read-only views of litigation's observed graph projection."""

QUERIES = {
    "email_chronology": "MATCH (e:Email) RETURN e.source_id, e.subject, e.date ORDER BY e.date LIMIT 20",
    "sender_correspondence": "MATCH (c:Correspondent)-[:SENT]->(e:Email) RETURN c.identity, e.source_id, e.subject, e.date LIMIT 20",
    "recipient_correspondence": "MATCH (e:Email)-[:TO]->(c:Correspondent) RETURN e.source_id, e.subject, c.identity LIMIT 20",
    "document_inventory": "MATCH (d:Document) RETURN d.source_id, d.filename, d.doc_type LIMIT 20",
}
