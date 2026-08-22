import pandas as pd

FILE_PATH = "./ml/data/fraud_transactions.csv"

def inspect_dataset():
    df = pd.read_csv(FILE_PATH)
    print("===Head===")
    print(df.head())
    print("===Shape===")
    print(df.shape)
    print("===Columns===")
    print(df.columns.tolist())
    print("===Missing Values===")
    print(df.isnull().sum())
    print("===Data Types===")
    print(df.dtypes)
    print("===Label Distribution===")
    print(df['fraudLabel'].value_counts(normalize=True)*100)
    print("===Transaction Types===")
    print(df['transactionType'].value_counts())
    print("===Amount Stats===")
    print(df['amount'].describe())

if __name__ == "__main__":
    inspect_dataset()
