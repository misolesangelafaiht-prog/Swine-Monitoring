import numpy as np
import pickle
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

print("Training ML model...")
np.random.seed(42)
X = []
y = []

for i in range(700):
    t = np.random.uniform(38.0, 40.0)
    X.append([t, t-0.5, 0.1, t-0.3, t+0.2])
    y.append("NORMAL")

for i in range(200):
    t = np.random.uniform(40.0, 40.5)
    X.append([t, t-0.5, 0.3, t-0.3, t+0.2])
    y.append("ELEVATED")

for i in range(200):
    t = np.random.uniform(40.5, 42.5)
    X.append([t, t-0.8, 0.6, t-0.5, t+0.3])
    y.append("FEVER")

X = np.array(X)
y = np.array(y)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
acc = accuracy_score(y_test, model.predict(X_test))
print("Accuracy: " + str(round(acc * 100, 1)) + "%")

with open("/home/pi/swine_monitor/pig_model.pkl", "wb") as f:
    pickle.dump(model, f)

print("Model saved!")
