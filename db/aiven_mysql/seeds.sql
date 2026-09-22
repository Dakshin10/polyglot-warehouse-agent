-- Seed Reference Data for Aiven MySQL
INSERT INTO warehouses (warehouse_name, location_city, synthetic_reference_data)
VALUES 
  ('Central Distribution Center', 'Seattle', 1),
  ('East Coast Fulfilment Center', 'Boston', 1),
  ('LATAM Regional Hub', 'Sao Paulo', 1);

INSERT INTO shipping_providers (provider_name, active_flag)
VALUES 
  ('FedEx Freight', 1),
  ('UPS Supply Chain', 1),
  ('DHL Express', 1);
