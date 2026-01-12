import time
from langchain_astradb import AstraDBVectorStore
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from flipkart.data_converter import DataConverter
from flipkart.config import Config
from astrapy.exceptions.data_api_exceptions import DataAPIHttpException

# Initialize embeddings
embedding = HuggingFaceEndpointEmbeddings(
    model=Config.EMBEDDING_MODEL
)

# Initialize vector store with retry logic
def initialize_vector_store(max_retries=5, wait_time=30):
    """Initialize AstraDB with retry logic for database startup"""
    
    for attempt in range(max_retries):
        try:
            print(f"Connecting to AstraDB (attempt {attempt + 1}/{max_retries})...")
            
            vstore = AstraDBVectorStore(
                embedding=embedding,
                collection_name="flipkart_database",
                api_endpoint=Config.ASTRA_DB_API_ENDPOINT,
                token=Config.ASTRA_DB_APPLICATION_TOKEN,
                namespace=Config.ASTRA_DB_KEYSPACE
            )
            
            print("✓ Successfully connected to AstraDB!")
            return vstore
            
        except DataAPIHttpException as e:
            if "502" in str(e) or "503" in str(e):
                if attempt < max_retries - 1:
                    print(f"⏳ Database is starting up... waiting {wait_time} seconds")
                    time.sleep(wait_time)
                else:
                    print("\n❌ Database failed to start after multiple attempts")
                    raise
            else:
                raise

# Safe document ingestion with retry logic
def safe_add_documents(vstore, docs, batch_size=50, max_retries=3):
    """Safely add documents with retry logic and batching"""
    
    total_docs = len(docs)
    print(f"\nAdding {total_docs} documents in batches of {batch_size}...")
    
    for i in range(0, total_docs, batch_size):
        batch = docs[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_docs + batch_size - 1) // batch_size
        
        for attempt in range(max_retries):
            try:
                vstore.add_documents(batch)
                print(f"✓ Batch {batch_num}/{total_batches} added ({len(batch)} docs)")
                break  # Success, move to next batch
                
            except DataAPIHttpException as e:
                if "502" in str(e) or "503" in str(e):
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 15  # 15s, 30s, 45s
                        print(f"⚠ Database busy, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        print(f"❌ Failed batch {batch_num} after {max_retries} attempts")
                        raise
                else:
                    raise
                    
            except Exception as e:
                print(f"❌ Unexpected error in batch {batch_num}: {e}")
                raise
        
        # Brief pause between batches
        if i + batch_size < total_docs:
            time.sleep(2)
    
    print(f"\n✓ All {total_docs} documents added successfully!")

# Check if data already exists
def check_existing_data(vstore):
    """Check if collection already has data"""
    try:
        count = vstore.astra_env.collection.count_documents({}, limit=1)
        return count > 0
    except:
        return False


# ============================================================
# DataIngestor Class - Main Interface
# ============================================================

class DataIngestor:
    """Main class for data ingestion operations"""
    
    def __init__(self, vector_store=None):
        """
        Initialize DataIngestor
        
        Args:
            vector_store: Optional pre-initialized vector store
        """
        if vector_store is None:
            self.vector_store = initialize_vector_store()
        else:
            self.vector_store = vector_store
    
    def ingest(self, csv_path="data/flipkart_product_review.csv", load_existing=False):
        """
        Load and ingest data from CSV or use existing data
        
        Args:
            csv_path: Path to the CSV file
            load_existing: If True, skip ingestion if data exists
            
        Returns:
            The vector store instance
        """
        if load_existing and check_existing_data(self.vector_store):
            print("✓ Using existing data from database")
            try:
                count = self.vector_store.astra_env.collection.count_documents({})
                print(f"✓ Found {count} documents in database")
            except:
                print("✓ Database has existing data")
            return self.vector_store
        
        # Load and ingest new data
        print("\nLoading data from CSV...")
        docs = DataConverter(csv_path).convert()
        safe_add_documents(self.vector_store, docs)
        
        return self.vector_store
    
    def get_vector_store(self):
        """Return the initialized vector store"""
        return self.vector_store


# ============================================================
# CLI Execution (when running directly)
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("FLIPKART DATA INGESTION")
    print("=" * 60)
    
    # Initialize and ingest
    ingestor = DataIngestor()
    vector_store = ingestor.ingest(load_existing=False)
    
    # Verification
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)
    try:
        count = vector_store.astra_env.collection.count_documents({})
        print(f"✓ Total vectors stored: {count}")
    except Exception as e:
        print(f"⚠ Could not verify count: {e}")
    
    print("\n✓ Data ingestion complete!")
    print("=" * 60)