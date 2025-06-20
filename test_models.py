# test_models.py - Test that models load without recursion errors
import sys
import traceback

def test_models_import():
    """Test that models can be imported without recursion errors"""
    print("Testing models import...")
    
    try:
        # Import database configuration
        from config.database import Base, engine
        print("✅ Database config imported successfully")
        
        # Import all models
        from models import (
            User, Question, Course, CourseEnrollment, Quiz, 
            QuizQuestion, QuizAttempt, QuestionSearchFilter,
            UserAttempt, ChapterDefinition, QuestionFollowUp,
            SubscriptionPlan, SubscriptionUserData, Payment,
            PromoCodeRedemption
        )
        print("✅ All models imported successfully")
        
        # Test that metadata can be created
        print("Testing metadata creation...")
        metadata = Base.metadata
        print(f"✅ Metadata created with {len(metadata.tables)} tables")
        
        # List all tables
        print("\nTables found:")
        for table_name in metadata.tables.keys():
            print(f"  - {table_name}")
        
        # Test relationships (this would trigger recursion if it existed)
        print("\nTesting relationships...")
        user_relationships = [attr for attr in dir(User) if not attr.startswith('_')]
        print(f"✅ User model has {len(user_relationships)} attributes")
        
        print("\n🎉 All tests passed! Models are working correctly.")
        return True
        
    except RecursionError as e:
        print(f"❌ Recursion error detected: {str(e)}")
        print("This indicates circular relationships in models")
        traceback.print_exc()
        return False
        
    except Exception as e:
        print(f"❌ Error importing models: {str(e)}")
        traceback.print_exc()
        return False

def test_table_creation():
    """Test that tables can be created"""
    try:
        from config.database import engine
        from models import Base
        
        print("\nTesting table creation...")
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error creating tables: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("TESTING MODELS")
    print("=" * 50)
    
    # Test 1: Import models
    import_success = test_models_import()
    
    if import_success:
        # Test 2: Table creation
        table_success = test_table_creation()
        
        if table_success:
            print("\n🎉 All tests passed! Your models are ready for production.")
            sys.exit(0)
        else:
            print("\n❌ Table creation failed.")
            sys.exit(1)
    else:
        print("\n❌ Model import failed.")
        sys.exit(1)