import unittest
from unittest.mock import patch

from model_selection import construir_modelos_a_intentar, obtener_siguiente_modelo


class ModelSelectionTests(unittest.TestCase):
    def test_obtener_siguiente_modelo_balancea_uso_antes_de_repetir(self):
        modelos = [
            {"id": "m1", "nombre": "Modelo 1", "categoria": "de pago"},
            {"id": "m2", "nombre": "Modelo 2", "categoria": "gratis"},
            {"id": "m3", "nombre": "Modelo 3", "categoria": "de pago"},
        ]
        estado = {}

        with patch("model_selection.random.shuffle", side_effect=lambda seq: None):
            usados = [obtener_siguiente_modelo(estado, modelos)["id"] for _ in range(3)]
            siguiente = obtener_siguiente_modelo(estado, modelos)["id"]

        self.assertEqual(usados, ["m1", "m2", "m3"])
        self.assertEqual(siguiente, "m1")

    def test_construir_modelos_a_intentar_respeta_modelo_fijo(self):
        modelos = [
            {"id": "pago-a", "nombre": "Pago A", "categoria": "de pago"},
            {"id": "gratis-a", "nombre": "Gratis A", "categoria": "gratis"},
            {"id": "pago-b", "nombre": "Pago B", "categoria": "de pago"},
        ]

        with patch("model_selection.random.shuffle", side_effect=lambda seq: None):
            intentos = construir_modelos_a_intentar({}, modelos, "pago-b", usar_aleatorio=False)

        self.assertEqual(intentos[0]["id"], "pago-b")
        self.assertEqual([m["id"] for m in intentos[1:]], ["gratis-a", "pago-a"])

    def test_construir_modelos_a_intentar_rota_modelo_principal_en_auto(self):
        modelos = [
            {"id": "m1", "nombre": "Modelo 1", "categoria": "de pago"},
            {"id": "m2", "nombre": "Modelo 2", "categoria": "gratis"},
        ]
        estado = {}

        with patch("model_selection.random.shuffle", side_effect=lambda seq: None):
            primero = construir_modelos_a_intentar(estado, modelos, "m1", usar_aleatorio=True, queue_key="q")[0]["id"]
            segundo = construir_modelos_a_intentar(estado, modelos, "m1", usar_aleatorio=True, queue_key="q")[0]["id"]

        self.assertEqual(primero, "m1")
        self.assertEqual(segundo, "m2")


if __name__ == "__main__":
    unittest.main()
