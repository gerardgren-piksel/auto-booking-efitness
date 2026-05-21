import os

login = os.getenv("EFITNESS_LOGIN")
password = os.getenv("EFITNESS_PASSWORD")

if not login or not password:
    raise SystemExit("Brak sekretów EFITNESS_LOGIN lub EFITNESS_PASSWORD")

print("Sekrety są dostępne. Następny krok: logowanie i zapis.")


