# Contribution

Merci de votre intérêt pour Web Cloner ! Les contributions sont les bienvenues.

## Code de conduite

Respectez les autres contributeurs. Pas de harcèlement, pas de comportement toxique.

## Comment contribuer

### Signaler un bug
1. Vérifiez que le bug n'a pas déjà été signalé dans les [Issues](https://github.com/anomalyco/web_cloner/issues)
2. Ouvrez une nouvelle issue avec :
   - Titre clair et descriptif
   - Étapes détaillées pour reproduire
   - Comportement attendu vs réel
   - Environnement (OS, Python, navigateur)

### Proposer une fonctionnalité
1. Ouvrez une issue avec le label `enhancement`
2. Décrivez le besoin et le cas d'utilisation
3. Si accepté, vous pouvez soumettre une PR

### Soumettre du code

```bash
# 1. Fork le projet
# 2. Clonez votre fork
git clone https://github.com/votre-utilisateur/web_cloner.git
cd web_cloner

# 3. Créez une branche
git checkout -b feature/ma-fonctionnalite

# 4. Installez en dev
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
pip install -r requirements.txt

# 5. Faites vos modifications
# ...

# 6. Testez
python -m pytest tests/

# 7. Committez (message clair en anglais ou français)
git add .
git commit -m "feat: ajout du mode de clonage XYZ"

# 8. Poussez
git push origin feature/ma-fonctionnalite

# 9. Ouvrez une Pull Request sur GitHub
```

## Conventions de code

- **Python** : respectez PEP 8 (max 100 caractères par ligne)
- **Imports** : stdlib → tiers → local (séparés par ligne vide)
- **Typage** : utilisez les type hints (`def foo(x: int) -> str:`)
- **Docstrings** : français (comme le code existant)
- **Nommage** : `snake_case` pour fonctions/variables, `PascalCase` pour classes
- **Asynchrone** : utilisez `async/await` (comme le code existant)

## Structure des commits

Utilisez des préfixes clairs :
```
feat:     nouvelle fonctionnalité
fix:      correction de bug
docs:     documentation
refactor: refactoring sans changement fonctionnel
test:     ajout/modification de tests
chore:    maintenance (CI, config, dépendances)
style:    formatage (PEP 8, espaces...)
```

## Tests

```bash
# Lancer tous les tests
python -m pytest tests/

# Avec couverture
python -m pytest tests/ --cov=core --cov=webui --cov=utils --cov-report=term-missing

# Test spécifique
python -m pytest tests/test_crawler.py -v
```

## Guide de style

- Suivez le style du code existant
- Commentez le "pourquoi", pas le "quoi"
- Évitez les commentaires évidents
- Préférez les fonctions courtes et ciblées
